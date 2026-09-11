"""M5: the two passkey tables, the two flags, the origins and the mount.

Same principle as the M1 through M4 and M6 files. The package's own suite
already proves the WebAuthn ceremonies: that a challenge is a single use row and
is refused past its deadline whether or not DynamoDB has reclaimed it, that a
signature counter regression is refused and logged, that the origin and the RP
id are checked on every ceremony, that a user-verified passkey sets `amr` to
`["swk", "pin", "mfa"]` and is not challenged for a TOTP code, and that the last
passkey cannot be deleted by a user with no password. Re-asserting any of that
here would pin the package's behaviour twice and say nothing about this product.

What no test in the package can cover is the seams M5 adds here.

**The two tables**, checked against the constants and key schemas the package
exports, for the reason M2's three, M3's one, M4's two and M6's two are checked
that way. A key name copied from `webbpulse.identity.storage` into
`app/db/tables.py` and again into the `tables` map in `terraform/identity.tf` is
a copy that drifts, and a drifted key is a `ValidationException` on the first
registration rather than anything a type checker sees. `passkeys` carries a GSI,
so its index name and projection are worth pinning on their own:
`PASSKEY_CREDENTIAL_INDEX` is a literal in the package and DynamoDB resolves an
index by name, so a rename on either side is a failed Query on the login path.

**Their opposite TTLs**, which are two decisions rather than one omission.
`webauthn-challenges` expires because a challenge nobody came back for is
litter; `passkeys` must never expire because a passkey is a sign-in method and
may be the only one, so a TTL there is a silent permanent lockout. This is the
same pairing `oauth-states` and `oauth-links` make, and it is asserted here for
the same reason: the two tables sit next to each other in three files and the
difference between them is one line in each.

**THE CONDITIONAL MOUNT, WHICH IS THE POINT OF THIS FILE.** M5's condition is
three things at once and this product controls two of them from two different
places. The stores are supplied unconditionally by the composition root; the
flag comes from `IDENTITY_PASSKEYS_ENABLED`, which Terraform renders from a
variable defaulting to false.

**The package defaults `passkeys_enabled` to `True` and this product ships it
`False`,** which makes this the one adoption in the series where an omitted
environment variable is not a no-op: it mounts seven routes rather than none.
That inversion is asserted directly below, because it is the whole reason the
Terraform variable is set explicitly rather than left out, and a future edit
that "tidies up" the explicit `false` would be a silent seven-route deploy.

**`passkeys_passwordless` is a second, independent switch**, and the pair of
tests on it exists because the two flags read like one. With `passkeys_enabled`
true and `passkeys_passwordless` false, the five management routes mount and
both `/login/passkey/*` routes still mount but refuse at the flow layer: a
passkey is a credential and a second factor but not an entry point. That refusal
is the package's and is not re-proved here; what is proved is that the setting
reaches the package as false, which is the part this product owns.

**The origins**, because `IDENTITY_WEBAUTHN_ORIGINS` is a JSON array of a list
field, and the class refuses bare comma separated values for those. A string
that Terraform rendered as CSV would be a `ValidationError` at cold start, and
an empty list would make the origin check vacuous, which is the whole of what
makes a passkey phishing resistant.

**A registration options round trip** against the in-memory stores, which is the
one end-to-end assertion here. It goes through the package's real
`PasskeyService` with this product's real settings and proves the three things
composition can get wrong that a route count cannot see: that the settings this
product builds are ones the ceremony accepts at all, that the challenge is
written to the store the composition root bound, and that the options carry this
product's RP id and name rather than the package's empty defaults.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI

from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN, FakeKms

PASSKEY_MANAGEMENT_POST_PATHS = (
    "/api/auth/passkeys/register/options",
    "/api/auth/passkeys/register/verify",
)
PASSKEY_MANAGEMENT_GET_PATHS = ("/api/auth/passkeys",)
PASSKEY_MANAGEMENT_PATCH_PATHS = ("/api/auth/passkeys/{credential_id}",)
PASSKEY_MANAGEMENT_DELETE_PATHS = ("/api/auth/passkeys/{credential_id}",)

PASSKEY_LOGIN_POST_PATHS = (
    "/api/auth/login/passkey/options",
    "/api/auth/login/passkey/verify",
)

ALL_PASSKEY_PATHS = frozenset(
    PASSKEY_MANAGEMENT_POST_PATHS
    + PASSKEY_MANAGEMENT_GET_PATHS
    + PASSKEY_MANAGEMENT_PATCH_PATHS
    + PASSKEY_MANAGEMENT_DELETE_PATHS
    + PASSKEY_LOGIN_POST_PATHS
)

RP_ID = "staging.webbpulse.com"
RP_NAME = "WebbPulse Portfolio"
WEBAUTHN_ORIGIN = "https://staging.webbpulse.com"


def test_the_passkey_table_names_are_the_packages_own_constants() -> None:
    """Neither name is retyped here, in Terraform, or in the package."""
    import webbpulse.identity as package

    from app.db import tables

    assert tables.PASSKEYS == package.PASSKEYS_TABLE
    assert tables.WEBAUTHN_CHALLENGES == package.WEBAUTHN_CHALLENGES_TABLE


def test_the_passkey_table_is_keyed_for_a_consistent_listing() -> None:
    """Hash `user_id`, range `credential_id`, which is the direction that matters.

    The management page reads its own writes, so listing a user's credentials
    has to be a Query on the base table, where a consistent read is available.
    Keyed the other way round it would have to be a GSI query, and DynamoDB
    offers no consistent read on a GSI at all.
    """
    from app.db.tables import TABLES

    spec = TABLES["passkeys"]
    assert spec["KeySchema"] == [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "credential_id", "KeyType": "RANGE"},
    ]


def test_the_passkey_table_carries_the_credential_index_the_package_names() -> None:
    """The login lookup's index, by the package's own literal, projecting ALL.

    DynamoDB resolves an index by name, so a rename on either side is a failed
    Query on the sign-in path rather than a plan diff. The projection is ALL
    because the login path reads the stored public key and the sign count
    straight off the index, and KEYS_ONLY would buy a second read per sign in.
    """
    import webbpulse.identity as package

    from app.db.tables import TABLES

    indexes = TABLES["passkeys"]["GlobalSecondaryIndexes"]
    assert len(indexes) == 1
    assert indexes[0]["IndexName"] == package.PASSKEY_CREDENTIAL_INDEX
    assert indexes[0]["KeySchema"] == [
        {"AttributeName": "credential_id", "KeyType": "HASH"}
    ]
    assert indexes[0]["Projection"] == {"ProjectionType": "ALL"}


def test_the_challenge_table_is_keyed_on_the_challenge_and_nothing_else() -> None:
    """One row is one in-flight ceremony, read by primary key and no other way."""
    from app.db.tables import TABLES

    spec = TABLES["webauthn-challenges"]
    assert spec["KeySchema"] == [{"AttributeName": "challenge_id", "KeyType": "HASH"}]
    assert "GlobalSecondaryIndexes" not in spec


def test_the_two_passkey_tables_expire_opposite_things() -> None:
    """The challenge expires; the passkey must never.

    A TTL on `passkeys` would remove a sign-in method on DynamoDB's reclaim
    schedule rather than on any deadline a person chose, which for a user whose
    passkey is their only credential is a permanent lockout. The assertion is
    made against `ALL_TABLES`, which is what `conftest.py` and
    `scripts/create_local_tables.py` both walk, so it pins the value that is
    actually used rather than a restatement of it.
    """
    from app.db.tables import ALL_TABLES, IDENTITY_TTL_ATTRIBUTE

    ttls = dict(ALL_TABLES)
    assert ttls["webauthn-challenges"] == IDENTITY_TTL_ATTRIBUTE
    assert ttls["passkeys"] is None


def test_both_passkey_tables_are_created_by_the_suite(aws_tables: Any) -> None:
    """A table the package writes to that the suite does not create is a suite
    that cannot exercise a single M5 flow.

    `aws_tables` is this repository's own fixture and it builds every table in
    `ALL_TABLES`, which is why adding the pair there is the whole of what makes
    them exist for the suite."""
    del aws_tables

    from app.db.tables import ALL_TABLES

    names = {name for name, _ in ALL_TABLES}
    assert {"passkeys", "webauthn-challenges"} <= names


def test_the_package_defaults_both_passkey_flags_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE PACKAGE SHIPS THESE ON AND THIS PRODUCT SHIPS THEM OFF.

    This is the assertion the rest of the file rests on. Every other identity
    flag this product sets explicitly happens to agree with the package's
    default, so omitting the Terraform line would be harmless; these two do not.
    An unset `IDENTITY_PASSKEYS_ENABLED` mounts seven routes.

    Pinning the package's default here rather than trusting the comment means a
    future release that flips it to false turns the now-redundant Terraform line
    into a failing test that says so, instead of leaving a line nobody can
    explain.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.delenv("IDENTITY_PASSKEYS_ENABLED", raising=False)
    monkeypatch.delenv("IDENTITY_PASSKEYS_PASSWORDLESS", raising=False)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.passkeys_enabled is True
    assert settings.passkeys_passwordless is True


def test_the_flags_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terraform renders `tostring(var...)`, and pydantic reads that back.

    The rendered strings are what `lambda_domains.tf` actually sets, so this is
    the seam between a Terraform bool and a pydantic one.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true")
    monkeypatch.setenv("IDENTITY_PASSKEYS_PASSWORDLESS", "false")

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.passkeys_enabled is True
    assert settings.passkeys_passwordless is False


def test_the_shipping_values_turn_both_flags_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What both environments deploy today: enabled false, passwordless false."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.passkeys_enabled is False
    assert settings.passkeys_passwordless is False


def test_the_webauthn_origins_are_read_as_a_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A list field, so the environment form is JSON and never bare CSV.

    `IdentitySettings` refuses comma separated values for its list fields, so a
    Terraform expression that rendered `"https://a,https://b"` would be a
    `ValidationError` at cold start rather than a silently split pair. That is
    the behaviour worth pinning: the origin check is what makes a passkey
    phishing resistant, and a half-parsed origin list is not a check.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.webauthn_origins == [WEBAUTHN_ORIGIN]


def test_the_origin_is_an_origin_and_not_a_url_with_a_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheme, host and optional port only, which is what a browser sends.

    `clientDataJSON` carries the origin, never a path, so an entry with a path
    can never match and would fail every ceremony with an origin mismatch.
    """
    from urllib.parse import urlparse

    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    for origin in settings.webauthn_origins:
        parsed = urlparse(origin)
        assert parsed.scheme == "https"
        assert parsed.netloc
        assert parsed.path == ""
        assert not parsed.query and not parsed.fragment


def test_the_rp_id_is_the_registrable_domain_and_not_the_api_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IDENTITY_RP_ID` comes from the module, and is what the origin sits under.

    An rp_id has to be the origin's own domain or a registrable suffix of it, or
    every ceremony is refused by the browser before the server sees it. Asserting
    the relationship rather than the literal is what makes this survive a
    rename: it is the pair that has to hold, and the pair is assembled in two
    different Terraform files.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.rp_id == RP_ID
    for origin in settings.webauthn_origins:
        host = origin.removeprefix("https://").split(":", 1)[0]
        assert host == settings.rp_id or host.endswith(f".{settings.rp_id}")


def test_the_rp_name_is_the_product_name_a_browser_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A display string, and the one M5 is the first milestone to actually read.

    It was already set for M1's sake and had no reader; an empty value would
    have shown the user a blank product name in the browser's own passkey
    prompt, which is a trust decision made on that dialog.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.rp_name == RP_NAME


def test_the_composition_root_supplies_both_passkey_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both stores, unconditionally, whatever the flag says.

    Supplying them behind a check on the flag would put the switch in two places
    that could disagree, and disagreeing presents as a Terraform variable flipped
    to true that changes nothing, with no error anywhere to say why.
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
    assert stores.passkeys is not None
    assert stores.webauthn_challenges is not None


def test_the_passkey_stores_are_bound_to_the_right_tables(
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
    assert _logical_name_of(stores.passkeys) == "passkeys"
    assert _logical_name_of(stores.webauthn_challenges) == "webauthn-challenges"


def test_the_hooks_still_satisfy_the_packages_protocol() -> None:
    """M5 adds no hook, so this has to keep passing untouched.

    The rule the package could have asked a hook for and did not is that the last
    passkey cannot be deleted by a user with no password: it reads that from the
    `credentials` store, which is where the package's own password lives.
    """
    from webbpulse.identity import IdentityHooks

    from app.composition.identity_hooks import PortfolioIdentityHooks

    assert isinstance(PortfolioIdentityHooks(), IdentityHooks)


def test_no_passkey_route_mounts_with_the_flag_off(
    identity_app_passkeys_off: FastAPI,
) -> None:
    """What staging and production serve today: none of the seven.

    Asserted over every path rather than a sample, because the package mounts the
    seven in one call and a partial mount is not a state it can be in.
    """
    assert ALL_PASSKEY_PATHS & _all_paths(identity_app_passkeys_off) == set()


def test_the_other_identity_routes_still_mount_with_the_flag_off(
    identity_app_passkeys_off: FastAPI,
) -> None:
    """The M5 bump changes the served API not at all, which is the deploy claim.

    A sample of one route from each earlier milestone that this fixture actually
    mounts. If adopting 0.15.0 had disturbed the mounting of anything already
    serving, this is where it shows, and it is the assertion that makes this PR
    safe to deploy ahead of the frontend.

    M3's four email routes are deliberately not in the list. They mount only when
    an `email_sender` is supplied, and `build_email_sender` returns `None` on an
    empty `IDENTITY_EMAIL_FROM`, which is what this fixture's environment has.
    That is the same state a staging profile without custom domains deploys, so
    asserting their absence here would pin the SES switch rather than anything
    M5 touches.
    """
    paths = _all_paths(identity_app_passkeys_off)

    assert "/api/auth/.well-known/openid-configuration" in paths
    assert "/api/auth/.well-known/jwks.json" in paths
    assert "/api/auth/login" in paths
    assert "/api/auth/refresh" in paths
    assert "/api/auth/logout" in paths
    assert "/api/auth/login/totp" in paths


def test_the_seven_passkey_routes_mount_once_the_flag_is_on(
    identity_app_passkeys_on: FastAPI,
) -> None:
    """Flipping one environment variable is the whole of the switch.

    No code changes between this fixture and the one above, which is what makes
    turning passkeys on a configuration change: one HCP variable and a redeploy.
    """
    app = identity_app_passkeys_on

    assert set(PASSKEY_MANAGEMENT_POST_PATHS) <= _paths_for_method(app, "POST")
    assert set(PASSKEY_LOGIN_POST_PATHS) <= _paths_for_method(app, "POST")
    assert set(PASSKEY_MANAGEMENT_GET_PATHS) <= _paths_for_method(app, "GET")
    assert set(PASSKEY_MANAGEMENT_PATCH_PATHS) <= _paths_for_method(app, "PATCH")
    assert set(PASSKEY_MANAGEMENT_DELETE_PATHS) <= _paths_for_method(app, "DELETE")


def test_the_mounted_paths_are_the_packages_own_constants(
    identity_app_passkeys_on: FastAPI,
) -> None:
    """The literals at the top of this file are checked against the package.

    Every path here is a string this file typed out and the frontend will type
    again, so pinning them against the package's own constants is what stops the
    two drifting silently. The prefix is the issuer's path, which
    `build_identity_router` derives itself.
    """
    from webbpulse.identity.passkey_routes import (
        LOGIN_PASSKEY_OPTIONS_PATH,
        LOGIN_PASSKEY_VERIFY_PATH,
        PASSKEY_ITEM_PATH,
        PASSKEY_REGISTER_OPTIONS_PATH,
        PASSKEY_REGISTER_VERIFY_PATH,
        PASSKEYS_PATH,
    )

    prefix = "/api/auth"
    expected = {
        f"{prefix}{path}"
        for path in (
            PASSKEY_REGISTER_OPTIONS_PATH,
            PASSKEY_REGISTER_VERIFY_PATH,
            LOGIN_PASSKEY_OPTIONS_PATH,
            LOGIN_PASSKEY_VERIFY_PATH,
            PASSKEYS_PATH,
            PASSKEY_ITEM_PATH,
        )
    }

    assert expected == set(ALL_PASSKEY_PATHS)
    assert expected <= _all_paths(identity_app_passkeys_on)


def test_passwordless_off_is_what_the_enabled_app_still_ships(
    monkeypatch: pytest.MonkeyPatch, private_key: Any
) -> None:
    """Turning passkeys on does not turn passwordless on with it.

    The two login routes mount either way and refuse at the flow layer when
    passwordless is off, which is the package's own behaviour. What this asserts
    is the part this product owns: enabling the capability leaves the policy
    flag alone, so the rollout step and the policy decision stay separate.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true")

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.passkeys_enabled is True
    assert settings.passkeys_passwordless is False


def test_registration_options_round_trip_against_the_in_memory_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One real ceremony leg, with this product's settings and fake stores.

    The route-count tests above prove the seven routes exist; none of them proves
    the settings this product assembles are ones a ceremony will accept. This
    does, and it is the only test here that runs the package's real
    `PasskeyService`.

    Three things it pins that a mounted route cannot:

    - **The settings are usable.** The package requires `rp_id` and
      `webauthn_origins` rather than defaulting either, and raises naming the
      variable when one is missing. A product that rendered an empty origins
      array would pass every assertion above and fail on the first real
      enrolment.
    - **The challenge is written.** `begin_registration` puts a row in the
      challenge store, and the store it puts it in is the one that was passed. A
      challenge written nowhere is an enrolment that can never be finished.
    - **The options carry this product's identity.** `rp.id` and `rp.name` are
      what the browser shows the user and what gets hashed into the credential,
      and the package's defaults for both are empty strings.

    In-memory stores rather than DynamoDB because the seam under test is
    settings-to-ceremony, not storage; `webbpulse.identity.storage` provides the
    in-memory pair for exactly this.
    """
    from webbpulse.identity import (
        IdentitySettings,
        IdentityStores,
        InMemoryPasskeyStore,
        InMemoryWebAuthnChallengeStore,
    )
    from webbpulse.identity.passkeys import PasskeyService

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true")

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]
    challenges = InMemoryWebAuthnChallengeStore()
    stores = IdentityStores(
        passkeys=InMemoryPasskeyStore(),
        webauthn_challenges=challenges,
    )

    challenge = PasskeyService(settings, stores).begin_registration(
        "user-1", user_name="owner@webbpulse.com", display_name="Owner"
    )

    assert challenge.challenge_id
    assert challenges.consume(challenge.challenge_id) is not None

    options = challenge.options
    assert options["rp"]["id"] == RP_ID
    assert options["rp"]["name"] == RP_NAME
    assert options["challenge"]
    assert options["user"]["name"] == "owner@webbpulse.com"


def test_an_empty_origin_list_is_refused_rather_than_treated_as_allow_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty origin list raises naming the variable, and does not mean "any".

    This is the failure mode `IDENTITY_WEBAUTHN_ORIGINS` exists to prevent, and
    the reason the package requires the value instead of defaulting it. Pinned
    here because the Terraform local that renders it is one `jsonencode` away
    from producing `[]`, and a vacuous origin check is not a check.

    **The refusal is at verification, not at `begin_registration`.** The package
    reads the origins from a lazy property that only the two verify legs touch,
    so generating options against an empty list succeeds and it is the assertion
    that fails. That is worth pinning rather than glossing: it means a
    misconfigured environment presents as a registration that gets halfway and
    then fails, and the useful signal is the error naming the variable. The
    property is exercised directly here because reaching it through a verify leg
    would need a real authenticator response.
    """
    from webbpulse.identity import (
        IdentitySettings,
        IdentityStores,
        InMemoryPasskeyStore,
        InMemoryWebAuthnChallengeStore,
    )
    from webbpulse.identity.passkeys import PasskeyService

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true")
    monkeypatch.setenv("IDENTITY_WEBAUTHN_ORIGINS", json.dumps([]))

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]
    assert settings.webauthn_origins == []

    service = PasskeyService(
        settings,
        IdentityStores(
            passkeys=InMemoryPasskeyStore(),
            webauthn_challenges=InMemoryWebAuthnChallengeStore(),
        ),
    )

    with pytest.raises(ValueError, match="IDENTITY_WEBAUTHN_ORIGINS"):
        _ = service.origins


def test_the_configured_origins_reach_the_ceremony(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the test above: the deployed value is accepted and used.

    Asserting only the refusal would leave the ordinary path unproven, and the
    ordinary path is the one every sign in takes.
    """
    from webbpulse.identity import (
        IdentitySettings,
        IdentityStores,
        InMemoryPasskeyStore,
        InMemoryWebAuthnChallengeStore,
    )
    from webbpulse.identity.passkeys import PasskeyService

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true")

    service = PasskeyService(
        IdentitySettings(),  # pyright: ignore[reportCallIssue]
        IdentityStores(
            passkeys=InMemoryPasskeyStore(),
            webauthn_challenges=InMemoryWebAuthnChallengeStore(),
        ),
    )

    assert service.origins == [WEBAUTHN_ORIGIN]
    assert service.rp_id == RP_ID


class _Captured(Exception):
    """Unwinds `build_router` once the call it made has been captured."""


def _logical_name_of(store: Any) -> str:
    """The unprefixed table a Dynamo store's repository is pointed at.

    Reaches through the store's private `_repo` attribute deliberately, for the
    reason the M4 and M6 files' copies give: there is no public accessor, and the
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
    """The `IDENTITY_*` variables `terraform/lambda_domains.tf` sets, M5 included.

    The two passkey flags are set to the shipping `"false"` rather than deleted,
    because deleting them is not the deployed state: Terraform sets both
    explicitly, and the package's own default is the opposite value. A test that
    unset them would be asserting against an environment this product never
    produces. `test_the_package_defaults_both_passkey_flags_on` is the one place
    they are deliberately removed, and it removes them itself.
    """
    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", RP_ID)
    monkeypatch.setenv("IDENTITY_RP_ID", RP_ID)
    monkeypatch.setenv("IDENTITY_RP_NAME", RP_NAME)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "false")
    monkeypatch.setenv("IDENTITY_PASSKEYS_PASSWORDLESS", "false")
    monkeypatch.setenv("IDENTITY_WEBAUTHN_ORIGINS", json.dumps([WEBAUTHN_ORIGIN]))
    monkeypatch.delenv("IDENTITY_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("IDENTITY_GITHUB_CLIENT_ID", raising=False)


@pytest.fixture(scope="module")
def private_key() -> Any:
    """One 2048-bit key for the module, for the reason M2's copy gives: a module
    scoped fixture does not cross files."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _build_identity_app(
    monkeypatch: pytest.MonkeyPatch, private_key: Any, *, enabled: bool
) -> FastAPI:
    """The identity router as the composition root builds it, at this flag value.

    No AWS call is made: the `boto3.client` monkeypatch covers KMS as well as the
    other clients the root builds, and no passkey route is exercised, only
    counted.
    """
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true" if enabled else "false")

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))
    return app


@pytest.fixture
def identity_app_passkeys_off(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """The router exactly as staging and production serve it today."""
    return _build_identity_app(monkeypatch, private_key, enabled=False)


@pytest.fixture
def identity_app_passkeys_on(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """The router once the owner flips the one variable, after the frontend lands."""
    return _build_identity_app(monkeypatch, private_key, enabled=True)


def _paths_for_method(app: FastAPI, method: str) -> set[str]:
    return {
        route.path for route in app.routes if method in getattr(route, "methods", set())
    }


def _all_paths(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes if hasattr(route, "path")}
