"""M6: the two OAuth tables, the client id switch, the secrets and the new hook.

Same principle as the M1 through M4 files. The package's own suite already
proves the authorization code flow: that a `state` is single use, that PKCE is
generated and checked, that Google's ID token is verified against the published
JWKS, that GitHub's verified primary address is preferred over the profile
field, that auto-linking refuses unless both emails are verified, and that
`unlink` refuses to remove the last sign-in method. Re-asserting any of that here
would pin the package's behaviour twice and say nothing about this product.

What no test in the package can cover is the five seams M6 adds here.

**The two tables**, checked against the constants and key schemas the package
exports, for the reason M2's three, M3's one and M4's two are checked that way.
A key name copied from `webbpulse.identity.oauth` into `app/db/tables.py` and
again into the `tables` map in `terraform/identity.tf` is a copy that drifts,
and a drifted key is a `ValidationException` on the first sign in rather than
anything a type checker sees. `oauth-links` carries the first identity GSI since
`refresh-tokens`, so its index name and projection are worth pinning on their
own: `OAUTH_LINK_USER_INDEX` is a literal in the package and DynamoDB resolves
an index by name, so a rename on either side is a failed Query on the unlink
path.

**Their opposite TTLs**, which are two decisions rather than one omission.
`oauth-states` expires because an abandoned authorization is litter; `oauth-links`
must never expire because a link is a sign-in method and may be the only one, so
a TTL there is a silent permanent lockout.

**THE CONDITIONAL MOUNT, WHICH IS THE POINT OF THIS FILE.** M6's condition is
two things at once, and this product controls them from two different places.
The stores are supplied unconditionally by the composition root; the client ids
come from `IDENTITY_GOOGLE_CLIENT_ID` and `IDENTITY_GITHUB_CLIENT_ID`, which
`terraform/identity.tf` renders from variables that default to the empty string
because no OAuth app has been registered yet. So the deployed state today is
"stores present, no provider enabled", and the package declares none of the five
routes.

Both sides of that switch are asserted here, and the empty side is the one that
matters most: it is the claim that this adoption changes the served API not at
all until somebody registers an OAuth app, and it is the claim a reviewer of the
pull request is being asked to take on trust otherwise. A regression that mounted
the routes anyway would put five endpoints into the OpenAPI document that redirect
users to a provider with no `client_id`.

**The client secrets**, which travel outside the settings object on purpose.
They are keys of the single `webbpulse-<env>/app` secret rather than
`IDENTITY_*` variables, and `build_oauth_client_secrets` maps them onto the
provider names the package uses. Its behaviour when a key is absent is the
behaviour that keeps a deployment with no OAuth app from failing its cold start,
so it is pinned in both directions.

**The new hook.** `IdentityHooks.has_other_sign_in_method` is the first change
to the hooks protocol since M3. It has a default on `BaseIdentityHooks`, but
`PortfolioIdentityHooks` is not a subclass and satisfies the protocol
structurally, so the default does not reach it: without the method this product's
hooks stop satisfying `IdentityHooks`. The structural check is repeated here for
that reason, and the return value is pinned with the reasoning that chose it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI

from app.composition.identity_hooks import PortfolioIdentityHooks

from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN, FakeKms

OAUTH_GET_PATHS = (
    "/api/auth/oauth/{provider}/start",
    "/api/auth/oauth/callback",
    "/api/auth/oauth/links",
)
OAUTH_POST_PATHS = ("/api/auth/oauth/{provider}/link",)
OAUTH_DELETE_PATHS = ("/api/auth/oauth/{provider}/link",)

OAUTH_PROVIDERS_PATH_FULL = "/api/auth/oauth/providers"

GOOGLE_CLIENT_ID = "1234567890-abcdefghijklmnop.apps.googleusercontent.com"

GITHUB_CLIENT_ID = "Iv1.0123456789abcdef"

REDIRECT_URI = f"{ISSUER}/oauth/callback"


def test_the_oauth_table_names_are_the_packages_own_constants() -> None:
    """Copied names, checked against the source they were copied from."""
    from webbpulse.identity import OAUTH_LINKS_TABLE, OAUTH_STATES_TABLE

    from app.db import tables

    assert tables.OAUTH_STATES == OAUTH_STATES_TABLE
    assert tables.OAUTH_LINKS == OAUTH_LINKS_TABLE


def test_the_state_table_is_keyed_on_the_state_and_nothing_else() -> None:
    """Hash `state`, a string, no range key, no index.

    A callback arrives carrying the state, so every read here is a point read on
    the primary key. The row is spent by a conditional delete on that same key,
    which is what makes it single use even when two callbacks race.
    """
    from app.db.tables import TABLES

    spec = TABLES["oauth-states"]

    assert spec["KeySchema"] == [{"AttributeName": "state", "KeyType": "HASH"}]
    assert spec["AttributeDefinitions"] == [
        {"AttributeName": "state", "AttributeType": "S"}
    ]
    assert "GlobalSecondaryIndexes" not in spec


def test_the_link_table_is_keyed_on_the_provider_identity() -> None:
    """Hash `provider_subject`, a string, no range key.

    This is the load-bearing half of the design and not an arbitrary choice.
    Keying on `<provider>#<subject>` makes the uniqueness constraint the primary
    key, so attaching a provider is one conditional put on
    `attribute_not_exists(provider_subject)` and a race resolves to one winner
    with no read-then-write and no reservation rows. Keying it any other way
    would need this product to enforce uniqueness itself.
    """
    from app.db.tables import TABLES

    spec = TABLES["oauth-links"]

    assert spec["KeySchema"] == [
        {"AttributeName": "provider_subject", "KeyType": "HASH"}
    ]
    assert spec["AttributeDefinitions"] == [
        {"AttributeName": "provider_subject", "AttributeType": "S"},
        {"AttributeName": "user_id", "AttributeType": "S"},
    ]


def test_the_link_table_carries_the_user_index_the_package_names() -> None:
    """`user_id-index`, hash `user_id`, projecting ALL.

    The index name is a literal in the package, `OAUTH_LINK_USER_INDEX`, and
    DynamoDB resolves an index by name, so the two cannot merely be similar.
    A rename on either side is a failed Query on the listing route and, worse,
    on the last-method count in `unlink`, which is the check that stops a user
    deleting their only way in.

    `ALL` rather than `KEYS_ONLY` because the listing route renders the whole
    record, and a keys-only projection would buy a second read per link.
    """
    from webbpulse.identity import OAUTH_LINK_USER_INDEX

    from app.db.tables import TABLES

    indexes = TABLES["oauth-links"]["GlobalSecondaryIndexes"]

    assert len(indexes) == 1
    assert indexes[0]["IndexName"] == OAUTH_LINK_USER_INDEX
    assert indexes[0]["KeySchema"] == [{"AttributeName": "user_id", "KeyType": "HASH"}]
    assert indexes[0]["Projection"] == {"ProjectionType": "ALL"}


def test_the_two_oauth_tables_expire_opposite_things() -> None:
    """States expire, links never do, and both are decisions.

    An abandoned authorization is litter and reclaiming it is what the TTL is
    for; the package re-checks the ten minute deadline on every read, so the TTL
    is storage reclamation and never the access check.

    A link is a sign-in method and may be the only one a user has. A TTL there
    would delete it on DynamoDB's own schedule, which is a permanent lockout with
    nothing in any log at the moment it mattered, so `oauth-links` joins
    `credentials`, `totp-factors` and `recovery-codes` as a table that must
    never grow one.
    """
    from app.db.tables import ALL_TABLES

    ttls = dict(ALL_TABLES)

    assert ttls["oauth-states"] == "expires_at"
    assert ttls["oauth-links"] is None


def test_both_oauth_tables_are_created_by_the_suite() -> None:
    """Registered in `ALL_TABLES`, which is what `conftest` walks.

    A table in `TABLES` but not in `ALL_TABLES` is one no test can exercise and
    a `ResourceNotFoundException` the deployed stack does not have.
    """
    import boto3

    from app.config import settings
    from app.db.tables import ALL_TABLES

    names = dict(ALL_TABLES)
    assert "oauth-states" in names
    assert "oauth-links" in names

    live = set(boto3.client("dynamodb").list_tables()["TableNames"])
    prefix = settings.DYNAMODB_TABLE_PREFIX
    assert f"{prefix}-oauth-states" in live
    assert f"{prefix}-oauth-links" in live


def test_every_identity_table_the_package_names_is_registered_here() -> None:
    """The set Terraform's `tables` map has to match, named rather than counted.

    `terraform/identity.tf` passes the whole map rather than merging with the
    module default, so a table added here and not there is a table that exists
    in the test suite and not in the account. M6 is the release where that
    matters most: the module gained four tables in 2.8.0 and a consumer passing
    `tables` explicitly picks up none of them without writing them out.
    """
    from webbpulse.identity import (
        CREDENTIALS_TABLE,
        IDENTITY_TOKENS_TABLE,
        LOGIN_ATTEMPTS_TABLE,
        OAUTH_LINKS_TABLE,
        OAUTH_STATES_TABLE,
        RECOVERY_CODES_TABLE,
        REFRESH_TOKENS_TABLE,
        TOTP_FACTORS_TABLE,
    )

    from app.db.tables import TABLES

    identity_owned = {
        CREDENTIALS_TABLE,
        REFRESH_TOKENS_TABLE,
        LOGIN_ATTEMPTS_TABLE,
        IDENTITY_TOKENS_TABLE,
        TOTP_FACTORS_TABLE,
        RECOVERY_CODES_TABLE,
        OAUTH_STATES_TABLE,
        OAUTH_LINKS_TABLE,
    }

    assert identity_owned <= set(TABLES)


def test_the_client_ids_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IDENTITY_GOOGLE_CLIENT_ID` and `IDENTITY_GITHUB_CLIENT_ID` land on the fields.

    `IdentitySettings` is a `BaseSettings` with `env_prefix="IDENTITY_"` and this
    product passes it nothing, so the variable names in
    `terraform/lambda_domains.tf` and the field names in the package are joined
    by nothing but that prefix rule. A test that constructed the settings
    directly would not notice either side being renamed, and a renamed variable
    here is not an error: it is OAuth silently staying off after the owner
    thought they had switched it on.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    monkeypatch.setenv("IDENTITY_GITHUB_CLIENT_ID", GITHUB_CLIENT_ID)

    settings = IdentitySettings()

    assert settings.google_client_id == GOOGLE_CLIENT_ID
    assert settings.github_client_id == GITHUB_CLIENT_ID


def test_unset_client_ids_are_empty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Which is the deployed state today, and is a valid one rather than a fault.

    `terraform/identity.tf` renders both from variables that default to `""`, so
    the function has the variables set and empty. The package's default is the
    same empty string, so an unset variable and an empty one mean the same thing,
    which is what lets the Terraform stay unconditional.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()

    assert settings.google_client_id == ""
    assert settings.github_client_id == ""


def test_the_redirect_uri_allow_list_is_read_as_a_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IDENTITY_OAUTH_REDIRECT_URIS` is JSON, not comma separated values.

    `oauth_redirect_uris` is a list field, and `IdentitySettings` refuses bare
    CSV for its list fields, the same rule `IDENTITY_SIGNING_KEY_ARNS` follows.
    `terraform/identity.tf` builds it with `jsonencode`, so this pins that the
    two agree on the encoding as well as on the value.

    The value itself is the callback derived from the issuer, which is the
    string that also has to be registered with each provider. The package
    matches a requested `redirect_uri` against this list by exact string
    equality and never by prefix, so this is the whole of the product's side of
    that check.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_OAUTH_REDIRECT_URIS", json.dumps([REDIRECT_URI]))

    assert IdentitySettings().oauth_redirect_uris == [REDIRECT_URI]


def test_both_providers_are_enabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This product sets no `IDENTITY_OAUTH_PROVIDERS`, so the default is the list.

    Half of the mount condition is a setting nobody configures. `enabled_providers()`
    intersects this list with the providers carrying a client id, so if the
    package ever narrowed this default a provider would stop being offered on a
    deploy that changed no Terraform and no code.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    assert set(IdentitySettings().oauth_providers) == {"google", "github"}


def test_the_composition_root_supplies_both_oauth_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`oauth_states` and `oauth_links` are populated, not left at their defaults.

    Both default to `None`, and the package builds an `OAuthService` only when
    both are present. A bundle missing either would silently unmount all five
    routes while every other identity route kept working, which is the quietest
    possible way for M6 to be off, and it would look exactly like the intended
    "no client id" state.

    Asserted by intercepting the bundle the composition root actually builds,
    rather than by rebuilding one here, so it is this product's wiring under test
    and not a copy of it.
    """
    import boto3
    import webbpulse.identity as package
    from webbpulse.identity import DynamoOAuthLinkStore, DynamoOAuthStateStore

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)

    captured = _capture_build(monkeypatch, boto3, package)

    with pytest.raises(_Captured):
        build_router(Settings())

    assert isinstance(captured["stores"].oauth_states, DynamoOAuthStateStore)
    assert isinstance(captured["stores"].oauth_links, DynamoOAuthLinkStore)


def test_the_oauth_stores_are_bound_to_the_right_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each store repository carries its own table's name.

    Two stores built in adjacent lines from a helper that takes a table name is
    exactly the shape a copy-paste swaps, and swapped stores fail at runtime with
    a `ValidationException` about a missing key rather than anything sooner.
    """
    import boto3
    import webbpulse.identity as package

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)

    captured = _capture_build(monkeypatch, boto3, package)

    with pytest.raises(_Captured):
        build_router(Settings())

    stores = captured["stores"]
    assert _logical_name_of(stores.oauth_states) == "oauth-states"
    assert _logical_name_of(stores.oauth_links) == "oauth-links"


def test_the_client_secrets_are_passed_as_an_argument_not_a_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`oauth_client_secrets` reaches `build_identity_router` as a keyword.

    The package takes them this way rather than as `IdentitySettings` fields so
    a client secret never lands on an object that a `repr`, a pydantic
    validation error or a log line would render. This pins that this product
    respects that seam rather than routing the secrets back through the
    environment.
    """
    import boto3
    import webbpulse.identity as package

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)

    captured = _capture_build(monkeypatch, boto3, package)

    with pytest.raises(_Captured):
        build_router(Settings())

    assert "oauth_client_secrets" in captured["kwargs"]


def test_no_secrets_arn_yields_an_empty_mapping() -> None:
    """No ARN configured means nothing to read, and that is a success.

    This is the local and test path. `build_oauth_client_secrets` must not raise
    and must not attempt a Secrets Manager call, because no OAuth route will be
    declared without a client id anyway.
    """
    from app.composition.identity import build_oauth_client_secrets
    from app.composition.settings import Settings

    settings = Settings(APP_SECRETS_ARN=None, app_secrets_arn="")

    assert build_oauth_client_secrets(settings) == {}


def test_only_the_providers_whose_secret_is_present_are_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One provider registered is a valid state, not a half-configured one.

    Registering Google before GitHub is the likely order, and the package mounts
    the routes with only Google enabled, so a mapping carrying only `google` has
    to be what this returns rather than a `github` key holding an empty string.
    An empty-string secret would make the token exchange fail with a message
    about credentials instead of the package's own 503.
    """
    import app.composition.identity as composition
    from app.composition.settings import Settings

    monkeypatch.setattr(
        composition,
        "build_oauth_client_secrets",
        composition.build_oauth_client_secrets,
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.secrets",
        _FakeSecretsModule(
            {
                "SECRET_KEY": "x",
                "OAUTH_GOOGLE_CLIENT_SECRET": "google-secret",
            }
        ),
    )

    settings = Settings(APP_SECRETS_ARN="arn:aws:secretsmanager:us-west-2:1:secret:x")

    assert composition.build_oauth_client_secrets(settings) == {
        "google": "google-secret"
    }


def test_a_secret_with_no_oauth_keys_yields_an_empty_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deployed state today: a real secret that carries no OAuth key.

    Returning `{}` rather than raising is what keeps the identity function's cold
    start working before any OAuth app exists. The alternative, treating a
    missing key as a misconfiguration, would make adopting M6 a change that could
    not be deployed until the owner had finished registering both providers.
    """
    import app.composition.identity as composition
    from app.composition.settings import Settings

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.secrets",
        _FakeSecretsModule({"SECRET_KEY": "x", "ADMIN_USERNAME": "admin"}),
    )

    settings = Settings(APP_SECRETS_ARN="arn:aws:secretsmanager:us-west-2:1:secret:x")

    assert composition.build_oauth_client_secrets(settings) == {}


def test_the_oauth_secret_keys_are_upper_case_like_every_other_secret_key() -> None:
    """The secret's keys are one convention, and this is what holds them to it.

    Every lookup against the app secret is `loaded.get(name)` against a plain
    dict, here and in `Settings._resolve_secret`, so the match is exact. The four
    keys `terraform/db.tf` has always written are upper case, and these two are
    written by the same `json` block in the same module, so a lower case name
    here would be a key that is in Secrets Manager and never found.

    That failure is silent in the worst way. Both client ids set, both secrets
    present, `build_oauth_client_secrets` returning `{}`, and from webbpulse
    0.16.0 a `GET /api/auth/oauth/providers` answering `{"providers": []}`
    because a provider is only listed when it has both halves. No exception, no
    log line, just a sign-in page with no buttons on it.

    Asserting the convention rather than the two literal names on purpose: the
    names themselves are asserted by the test above that reads one out of a fake
    secret, and what this protects is the rule that the next provider added to
    the mapping has to follow.
    """
    from app.composition.identity import OAUTH_SECRET_KEYS

    assert OAUTH_SECRET_KEYS
    for provider, key in OAUTH_SECRET_KEYS.items():
        assert key == key.upper(), f"{provider} maps to a non upper case key: {key}"
        assert provider == provider.lower(), provider


def test_the_hooks_still_satisfy_the_packages_protocol() -> None:
    """M6 adds a hook, and this is the check that would have caught its absence.

    `PortfolioIdentityHooks` is not a `BaseIdentityHooks` subclass, so the
    package's `False` default does not reach it: it satisfies `IdentityHooks`
    structurally, and a protocol that grew a method it lacks is a protocol it no
    longer satisfies. Without `has_other_sign_in_method` this assertion fails,
    which is exactly the failure that keeps the deployed function from raising
    `AttributeError` partway through an unlink.
    """
    from webbpulse.identity import IdentityHooks

    assert isinstance(PortfolioIdentityHooks(), IdentityHooks)


def test_the_product_reports_no_sign_in_method_the_package_cannot_see() -> None:
    """`False`, because Portfolio genuinely holds none.

    Every way into this product is either the M2 password credential or an M6
    OAuth link, and `OAuthService.unlink` counts both of those itself before it
    calls this. Passkeys are M5 and are not adopted, so the `passkeys` table
    `terraform/identity.tf` creates is empty and there is nothing there to
    count.

    Pinned rather than left implicit because the value has to change on the day
    M5 lands: a user holding a passkey and no password needs this to answer
    `True`, or `unlink` deletes their last OAuth link and locks them out
    permanently. A test asserting the current answer is what makes that a
    deliberate edit rather than a forgotten one.
    """
    hooks = PortfolioIdentityHooks()

    assert hooks.has_other_sign_in_method("1") is False
    assert hooks.has_other_sign_in_method("does-not-exist") is False


def test_no_oauth_route_mounts_without_a_client_id(
    identity_app_without_providers: FastAPI,
) -> None:
    """THE DEPLOYED STATE. Both stores supplied, neither client id set, no routes.

    This is the claim the pull request makes about being safe to apply before the
    owner registers anything, and it is the one worth a test rather than a
    sentence. The composition root supplies both OAuth stores unconditionally, so
    the only thing keeping the five routes out of the OpenAPI document is
    `enabled_providers()` coming back empty, and that is a package behaviour this
    product depends on rather than one it implements.

    A regression here is five endpoints that hand a user to Google with no
    `client_id` and land them on a provider error page.

    The match is on `/api/auth/oauth`, not on `oauth` anywhere in the path, so
    that FastAPI's own `/docs/oauth2-redirect` Swagger helper does not read as an
    identity route. That helper is mounted by `FastAPI()` itself and has nothing
    to do with this feature.

    `/api/auth/oauth/providers` is excluded, and that exclusion is the one thing
    webbpulse 0.16.0 changed about this assertion. Discovery mounts in every
    deployment by design, including this one, and answers `{"providers": []}`
    here; the test below is the one that pins it. Everything else about the claim
    stands: no flow route, so nothing that can hand a user to a provider.
    """
    paths = _all_paths(identity_app_without_providers)

    mounted = [
        path
        for path in paths
        if path.startswith("/api/auth/oauth") and path != OAUTH_PROVIDERS_PATH_FULL
    ]

    assert not mounted


def test_the_other_identity_routes_still_mount_without_a_client_id(
    identity_app_without_providers: FastAPI,
) -> None:
    """Turning OAuth off turns nothing else off.

    The M6 mount sits before the email early-return inside the package, which is
    the kind of ordering that can unmount a later group by accident. `/login` and
    `/refresh` standing in for the M2 flows, and the discovery document standing
    in for M1, are enough to say the rest of the router is untouched.
    """
    paths = _all_paths(identity_app_without_providers)

    assert "/api/auth/login" in paths
    assert "/api/auth/refresh" in paths
    assert "/api/auth/.well-known/openid-configuration" in paths


def test_the_five_oauth_routes_mount_once_a_client_id_is_set(
    identity_app_with_providers: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/oauth/...` and not at the origin.

    The other half of the switch. Setting one variable is the whole of what the
    owner has to do in this repository, so this is the test that says the wiring
    behind that variable is complete: the stores, the settings and the secrets
    argument are all already in place, and the routes appear with no code change.

    Mounted under the issuer's path like every other identity route, because
    `build_identity_router` places itself there and `wiring.py` adds no prefix.
    """
    app = identity_app_with_providers

    for path in OAUTH_GET_PATHS:
        assert path in _paths_for_method(app, "GET"), path
    for path in OAUTH_POST_PATHS:
        assert path in _paths_for_method(app, "POST"), path
    for path in OAUTH_DELETE_PATHS:
        assert path in _paths_for_method(app, "DELETE"), path


def test_the_mounted_paths_are_the_packages_own_constants(
    identity_app_with_providers: FastAPI,
) -> None:
    """The deliberate opposite of the literals above.

    The tuples at the top of this file are written out so a moved route is
    noticed; this compares them against the package's constants so a renamed one
    is noticed too. `terraform/apigateway.tf` carries route keys built the same
    way, and a path that changed in the package without changing there is a 404
    at the gateway that no test in this file would otherwise see.
    """
    from webbpulse.identity import (
        OAUTH_CALLBACK_PATH,
        OAUTH_LINK_PATH,
        OAUTH_LINKS_PATH,
        OAUTH_START_PATH,
    )

    prefix = "/api/auth"

    assert f"{prefix}{OAUTH_START_PATH}" in OAUTH_GET_PATHS
    assert f"{prefix}{OAUTH_CALLBACK_PATH}" in OAUTH_GET_PATHS
    assert f"{prefix}{OAUTH_LINKS_PATH}" in OAUTH_GET_PATHS
    assert f"{prefix}{OAUTH_LINK_PATH}" in OAUTH_POST_PATHS


def test_provider_discovery_mounts_with_no_client_id_set(
    identity_app_without_providers: FastAPI,
) -> None:
    """THE DEPLOYED STATE, and the one OAuth route that is in it.

    Every other route in this file is conditional on a client id. This one is
    not, and that is the whole design: a sign-in page needs one authoritative
    answer to "which providers", and a route that is absent when OAuth is off
    gives a 404 that cannot be told apart from a routing mistake or a frontend
    talking to an older backend. An empty list says "none, and I am sure".
    """
    assert OAUTH_PROVIDERS_PATH_FULL in _paths_for_method(
        identity_app_without_providers, "GET"
    )


def test_provider_discovery_answers_an_empty_list_when_unconfigured(
    identity_app_without_providers: FastAPI,
) -> None:
    """It answers, it answers 200, and the list is empty.

    The mount test above says the route is in the table; this one calls it,
    because a route that is declared and raises on its first request is a
    regression the path assertion cannot see. It is also the assertion the
    frontend's switch away from probing rests on: `oauthAvailability.ts` now
    renders buttons straight from this body, so an unconfigured deployment
    showing no buttons is exactly this `[]` and nothing else.

    Anonymous, deliberately. No credential is sent and none is needed, which is
    what lets the sign-in page fetch it before anybody has signed in.
    """
    from fastapi.testclient import TestClient

    with TestClient(identity_app_without_providers) as client:
        response = client.get(OAUTH_PROVIDERS_PATH_FULL)

    assert response.status_code == 200
    assert response.json() == {"providers": []}


def test_provider_discovery_is_publicly_cacheable(
    identity_app_without_providers: FastAPI,
) -> None:
    """`Cache-Control: public, max-age=300`, which is why this is cheap to call.

    The frontend fetches this on every sign-in page load. The header is what
    keeps that off the Lambda for five minutes at a time, and `public` is sound
    because the body is configuration and holds nothing about any user. Pinned
    here because dropping it would turn one fetch per five minutes into one per
    page load with nothing failing to say so.
    """
    from fastapi.testclient import TestClient

    with TestClient(identity_app_without_providers) as client:
        response = client.get(OAUTH_PROVIDERS_PATH_FULL)

    assert response.headers["cache-control"] == "public, max-age=300"


def test_provider_discovery_lists_nothing_without_the_client_secrets(
    identity_app_with_providers: FastAPI,
) -> None:
    """Both client ids set, no secret in the blob, and still an empty list.

    0.16.0 is stricter than `enabled_providers()` on purpose: a provider is
    advertised only when it has **both** an id and a secret. Before that rule, an
    id with no secret was a button that sent a user to Google and met a 503 on
    the way back.

    `_build_identity_app` sets the two ids and supplies no secret, so this is
    precisely that half-configured state, and it is the state this repository
    would be in if `terraform/db.tf` set the ids without the two new secret keys.
    The five flow routes mount, and discovery still says there is nothing to draw
    a button for.
    """
    from fastapi.testclient import TestClient

    assert "/api/auth/oauth/{provider}/start" in _paths_for_method(
        identity_app_with_providers, "GET"
    )

    with TestClient(identity_app_with_providers) as client:
        response = client.get(OAUTH_PROVIDERS_PATH_FULL)

    assert response.status_code == 200
    assert response.json() == {"providers": []}


def test_the_discovery_path_is_the_packages_own_constant() -> None:
    """The literal above against the package's constant, like the five below it.

    Same reasoning as `test_the_mounted_paths_are_the_packages_own_constants`: a
    path renamed in the package and not here is a 404 in staging that no other
    test in this file would catch.
    """
    from webbpulse.identity.oauth_routes import OAUTH_PROVIDERS_PATH

    assert f"/api/auth{OAUTH_PROVIDERS_PATH}" == OAUTH_PROVIDERS_PATH_FULL


def test_one_provider_is_enough_to_mount_the_routes(
    monkeypatch: pytest.MonkeyPatch, private_key: Any
) -> None:
    """Google alone mounts all five, which is the likely first state.

    The routes are not per provider: `/oauth/{provider}/start` is one route that
    refuses an unknown provider with a 404, so registering one app is enough for
    the whole group to exist. A user is offered only what the frontend renders,
    which is a separate decision from what the router declares.
    """
    app = _build_identity_app(
        monkeypatch, private_key, google=GOOGLE_CLIENT_ID, github=""
    )

    assert "/api/auth/oauth/{provider}/start" in _paths_for_method(app, "GET")


class _Captured(Exception):
    """Unwinds `build_router` once the call it made has been captured."""


class _FakeSecretsModule:
    """Stands in for `app.secrets` so no Secrets Manager call is made.

    `build_oauth_client_secrets` imports the module inside the function, which is
    what makes replacing it in `sys.modules` enough. Injecting a client instead
    would exercise the shared loader's cache, which is process wide and would
    leak between tests.
    """

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def load_app_secrets(self, secret_arn: str, client: Any = None) -> dict[str, str]:
        del secret_arn, client
        return dict(self._values)


def _logical_name_of(store: Any) -> str:
    """The unprefixed table a Dynamo store's repository is pointed at.

    Reaches through the store's private `_repo` attribute deliberately, for the
    reason the M4 file's copy gives: there is no public accessor, and the
    alternative is not asserting the binding at all.
    """
    return str(store._repo.logical_name)


def _capture_build(
    monkeypatch: pytest.MonkeyPatch, boto3: Any, package: Any
) -> dict[str, Any]:
    """Intercept `build_identity_router` and record what the root passed it."""
    captured: dict[str, Any] = {}

    def capture(settings: Any, *args: Any, **kwargs: Any) -> Any:
        captured["stores"] = args[1] if len(args) > 1 else kwargs.get("stores")
        captured["kwargs"] = kwargs
        raise _Captured

    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: object())
    monkeypatch.setattr(package, "build_identity_router", capture)
    return captured


def _identity_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `IDENTITY_*` variables `terraform/lambda_domains.tf` sets.

    The two client ids are deliberately cleared rather than merely unset, so a
    variable left behind by another test cannot switch OAuth on underneath the
    "no provider" assertions, which are the ones this file exists for.
    """
    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_RP_ID", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_OAUTH_REDIRECT_URIS", json.dumps([REDIRECT_URI]))
    monkeypatch.delenv("IDENTITY_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("IDENTITY_GITHUB_CLIENT_ID", raising=False)


@pytest.fixture(scope="module")
def private_key() -> Any:
    """One 2048-bit key for the module, for the reason M2's copy gives: a module
    scoped fixture does not cross files."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_identity_app(
    monkeypatch: pytest.MonkeyPatch, private_key: Any, *, google: str, github: str
) -> FastAPI:
    """The identity router as the composition root builds it, with these ids set.

    No AWS call is made: the `boto3.client` monkeypatch covers KMS as well as the
    other clients the root builds, and no OAuth route is exercised, only counted.
    """
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    if google:
        monkeypatch.setenv("IDENTITY_GOOGLE_CLIENT_ID", google)
    if github:
        monkeypatch.setenv("IDENTITY_GITHUB_CLIENT_ID", github)

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))
    return app


@pytest.fixture
def identity_app_without_providers(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """The router exactly as staging and production serve it today."""
    return _build_identity_app(monkeypatch, private_key, google="", github="")


@pytest.fixture
def identity_app_with_providers(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """The router once the owner has registered both OAuth apps."""
    return _build_identity_app(
        monkeypatch, private_key, google=GOOGLE_CLIENT_ID, github=GITHUB_CLIENT_ID
    )


def _paths_for_method(app: FastAPI, method: str) -> set[str]:
    return {
        route.path for route in app.routes if method in getattr(route, "methods", set())
    }


def _all_paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes if hasattr(route, "path")}
