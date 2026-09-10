"""M2: the hooks, the tables and the six flow routes, as this product wires them.

Same principle as `test_identity_m1.py`: the package's own suite already proves
that rotation detects reuse, that lockout escalates and that the password policy
rejects a breached password, and re-asserting any of that here would pin the
package's behaviour twice. What no test in the package can cover is whether
*this* product's answers to the questions the package asks are the right ones,
and whether the tables it will write to actually exist with the keys it expects.

So this file covers three seams and nothing else.

**The hooks**, against the real `users` repository on moto. `PortfolioIdentityHooks`
is the whole of this product's identity policy, and every method of it is a
decision written down in section 8.2 rather than a mechanism. They are exercised
through the repository rather than a stub because the interesting failures are
schema failures: an integer id meeting a string `sub`, a lowercased email meeting
a case sensitive pointer item, a `create_user` that omits a column the table
requires.

**The table declarations**, against the constants the package exports. Every key
name, index name and TTL attribute in `app/db/tables.py` and in
`terraform/dynamodb.tf` is copied from `webbpulse.identity`, and a copy that is
never checked is a copy that drifts. A rename in the package should be a failing
test here, not a `ValidationException` in staging.

**The mount**, which is where M2 differs from M1 in the way that breaks things.
0.10.0 moved the prefix derivation into the package, so the composition root
mounts with no prefix and the six routes have to land under `/api/auth` anyway.
Getting that wrong doubles the path, which no type checker catches.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.composition.identity_hooks import (
    ADMIN_ROLE,
    REFUSAL_CODE,
    PortfolioIdentityHooks,
)
from app.db import entities

# The KMS fake, the issuer and the audience are M1's and are reused rather than
# re-declared: they are the values `terraform/lambda_domains.tf` sets, and a
# second copy of them here would be a second place for a rename to be missed.
# moto is not usable for the signing key, for the reason `test_identity_m1.py`
# gives at length: its asymmetric `get_public_key` returns a null `KeySpec`.
from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN, FakeKms

# The six flow paths, spelled out rather than imported from the package. The
# point of this list is to notice a path that moved, and a list derived from the
# thing it is checking cannot do that. `terraform/apigateway.tf` carries the same
# six as route keys and `tests/entrypoints/test_gateway_routes.py` pins those.
FLOW_PATHS = (
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/password",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/logout-all",
)


# ---------------------------------------------------------------------------
# The hooks
# ---------------------------------------------------------------------------


@pytest.fixture
def hooks() -> PortfolioIdentityHooks:
    """One instance, as the composition root builds one per process."""
    return PortfolioIdentityHooks()


def test_the_hooks_satisfy_the_protocol_structurally(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`isinstance` against the runtime checkable `Protocol`.

    This is the check that makes not inheriting from `BaseIdentityHooks` safe. A
    hook renamed in the package, or one this class never implemented, is caught
    here rather than at the first request that needs it.
    """
    from webbpulse.identity import IdentityHooks

    assert isinstance(hooks, IdentityHooks)


def test_an_active_administrator_may_authenticate(
    hooks: PortfolioIdentityHooks,
) -> None:
    """Returning `None` is how the protocol says yes."""
    assert hooks.may_authenticate({"is_admin": True, "is_active": True}) is None


@pytest.mark.parametrize(
    "user",
    [
        {"is_admin": False, "is_active": True},
        {"is_admin": True, "is_active": False},
        {"is_admin": False, "is_active": False},
        {},
    ],
    ids=["not-admin", "deactivated", "neither", "empty"],
)
def test_anything_but_an_active_administrator_is_refused(
    hooks: PortfolioIdentityHooks, user: dict[str, Any]
) -> None:
    """Section 8.2: this product's policy is `is_admin` and `is_active`, both.

    The empty mapping is in here on purpose. A user record missing both columns
    is the shape a bug produces, and the failing-closed reading is the one that
    refuses it.
    """
    from webbpulse.identity import AuthenticationRefused

    with pytest.raises(AuthenticationRefused) as raised:
        hooks.may_authenticate(user)

    assert raised.value.error_code == REFUSAL_CODE


def test_every_refusal_carries_the_same_message(
    hooks: PortfolioIdentityHooks,
) -> None:
    """Section 5.4: a refusal must not say which column failed.

    A message distinguishing "not an administrator" from "deactivated" tells an
    attacker that the address exists and that the password was right, which is
    the enumeration the identical-answer rule closes.
    """
    from webbpulse.identity import AuthenticationRefused

    messages = set()
    for user in ({"is_admin": False}, {"is_admin": True, "is_active": False}):
        with pytest.raises(AuthenticationRefused) as raised:
            hooks.may_authenticate(user)
        messages.add(raised.value.message)

    assert len(messages) == 1


def test_claims_are_the_admin_role_and_nothing_else(
    hooks: PortfolioIdentityHooks,
) -> None:
    """No username, no email, no registered claims.

    Section 3.3 keeps mutable identifiers out of a token, and the package drops
    any registered claim a hook returns rather than honouring it, so returning
    one would be silently ignored rather than loudly wrong.
    """
    claims = hooks.claims_for({"id": 1, "username": "admin", "email": "a@b.com"})

    assert dict(claims) == {"roles": [ADMIN_ROLE]}


def test_load_user_by_id_converts_the_string_sub_to_this_products_integer_id(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`sub` is a string and Portfolio's ids are integers from the counter."""
    created = entities.users.create(
        {"username": "someone", "email": "someone@webbpulse.com", "is_admin": True}
    )

    loaded = hooks.load_user_by_id(str(created["id"]))

    assert loaded is not None
    assert loaded["id"] == created["id"]


@pytest.mark.parametrize("sub", ["", "not-an-integer", "1.5", "99999"])
def test_load_user_by_id_answers_none_rather_than_raising(
    hooks: PortfolioIdentityHooks, sub: str
) -> None:
    """A `sub` this product did not mint is "no such user", not a 500.

    An unparsable id and an id with no row are the same answer deliberately: both
    mean the token names a user this service cannot produce, and distinguishing
    them would only tell a caller which kind of wrong their token is.
    """
    assert hooks.load_user_by_id(sub) is None


def test_load_user_by_email_finds_a_lowercase_address(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The ordinary case: the row was stored lowercase and the package sends
    lowercase, so the exact pointer lookup matches."""
    created = entities.users.create(
        {"username": "lower", "email": "lower@webbpulse.com"}
    )

    found = hooks.load_user_by_email("lower@webbpulse.com")

    assert found is not None
    assert found["id"] == created["id"]


def test_load_user_by_email_does_not_find_a_mixed_case_row(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The known gap, asserted rather than left to be discovered.

    Portfolio's uniqueness is a `UNIQUE#users#email#<value>` pointer written in
    whatever case the row carried, and the package guarantees a lowercased
    address. A row stored as `Mixed@...` is therefore not findable by M2 login.

    This is a deliberate limitation, not a bug to route around: trying a second
    casing would make "does this address have an account" answerable by spelling
    it two ways, which is the enumeration oracle section 5.4 closes. The fix is
    an `email_lower` column and a backfill at M9, when the cutover makes this the
    only login. `app/composition/identity_hooks.py` has the full argument.

    Until then the legacy `POST /api/v1/admin/login` still accepts the account:
    it looks up by username and is untouched by any of this.
    """
    entities.users.create({"username": "mixed", "email": "Mixed@WebbPulse.com"})

    assert hooks.load_user_by_email("mixed@webbpulse.com") is None


def test_load_user_by_email_answers_none_for_an_address_with_no_account(
    hooks: PortfolioIdentityHooks,
) -> None:
    assert hooks.load_user_by_email("nobody@webbpulse.com") is None


def test_create_user_returns_a_record_the_package_can_take_an_id_from(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`id` is what becomes `sub` and the credential's partition key."""
    user = hooks.create_user(email="new@webbpulse.com", attributes={})

    assert user["id"]
    assert hooks.load_user_by_id(str(user["id"])) is not None


def test_create_user_writes_a_non_administrator_that_cannot_then_sign_in(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The correct answer for a product with exactly one administrator.

    Registration succeeds and the account exists; `may_authenticate` then refuses
    it. That pair is why `IDENTITY_REGISTRATION_ENABLED` stays off, and the hook
    is implemented anyway so the route is a refusal rather than a 500 if it is
    ever switched on.
    """
    from webbpulse.identity import AuthenticationRefused

    user = hooks.create_user(email="new@webbpulse.com", attributes={})

    assert user["is_admin"] is False
    with pytest.raises(AuthenticationRefused):
        hooks.may_authenticate(user)


def test_create_user_stores_the_lowercased_address_it_was_given(
    hooks: PortfolioIdentityHooks,
) -> None:
    """So every row this milestone creates is findable by the lookup above."""
    user = hooks.create_user(email="new@webbpulse.com", attributes={})

    assert user["email"] == "new@webbpulse.com"
    assert hooks.load_user_by_email("new@webbpulse.com") is not None


def test_create_user_never_writes_the_legacy_password_column(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The password lives in `credentials`, which the package writes next.

    A placeholder in `hashed_password` would be a value the legacy flow's
    `verify_password` gets to compare against, and there is no placeholder worth
    that risk. A row with neither an M2 credential nor a legacy hash cannot be
    signed in by either flow, which is the safe shape.
    """
    user = hooks.create_user(
        email="new@webbpulse.com", attributes={"hashed_password": "injected"}
    )

    assert "hashed_password" not in user


def test_create_user_suffixes_a_username_that_is_already_taken(
    hooks: PortfolioIdentityHooks,
) -> None:
    """Portfolio requires a unique username and the package has no concept of one.

    Without the suffix the second registration for the same local part fails the
    whole `TransactWriteItems` on a pointer item the registrant cannot see or
    act on.
    """
    entities.users.create({"username": "taken", "email": "taken@elsewhere.com"})

    user = hooks.create_user(email="taken@webbpulse.com", attributes={})

    assert user["username"] == "taken2"


def test_create_user_ignores_an_id_supplied_through_attributes(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The counter allocates ids, and nothing reaching this hook may choose one.

    `attributes` is computed by the package from the registration request, and a
    product that let it set the primary key would let a request pick which row
    it overwrote.
    """
    user = hooks.create_user(email="new@webbpulse.com", attributes={"id": 4242})

    assert user["id"] != 4242


def test_on_user_created_does_nothing_and_says_so(
    hooks: PortfolioIdentityHooks,
) -> None:
    """No default rows and no email until M3. Raising here fails a registration."""
    assert hooks.on_user_created({"id": 1}, "password") is None


def test_user_repository_is_this_products_users_repository(
    hooks: PortfolioIdentityHooks,
) -> None:
    """No M2 flow calls this, and the protocol types it `object`.

    Asserted anyway because the identity function has to be able to answer the
    question at all: a hook that raised here would be a milestone's worth of
    debugging when a later flow first asks.
    """
    assert hooks.user_repository() is entities.users


# ---------------------------------------------------------------------------
# The table declarations
# ---------------------------------------------------------------------------


def test_the_table_names_are_the_packages_own_constants() -> None:
    """Copied names, checked against the source they were copied from."""
    from webbpulse.identity import (
        CREDENTIALS_TABLE,
        LOGIN_ATTEMPTS_TABLE,
        REFRESH_TOKENS_TABLE,
    )

    from app.db import tables

    assert tables.CREDENTIALS == CREDENTIALS_TABLE
    assert tables.REFRESH_TOKENS == REFRESH_TOKENS_TABLE
    assert tables.LOGIN_ATTEMPTS == LOGIN_ATTEMPTS_TABLE


def test_credentials_is_keyed_the_way_the_store_reads_it() -> None:
    """Hash `user_id`, range `credential_type`, both strings.

    `DynamoCredentialStore.get` builds exactly this key, and a mismatch is a
    `ValidationException` on the first login rather than anything a type checker
    sees.
    """
    from app.db.tables import TABLES

    spec = TABLES["credentials"]

    assert spec["KeySchema"] == [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "credential_type", "KeyType": "RANGE"},
    ]
    types = {
        attribute["AttributeName"]: attribute["AttributeType"]
        for attribute in spec["AttributeDefinitions"]
    }
    assert types == {"user_id": "S", "credential_type": "S"}


def test_refresh_tokens_carries_the_family_index_under_the_packages_name() -> None:
    """DynamoDB resolves an index by name, so the two cannot differ.

    The index is what `revoke_family` queries after reuse is detected, which is
    the operation the whole session design rests on.
    """
    from webbpulse.identity import REFRESH_FAMILY_INDEX

    from app.db.tables import TABLES

    spec = TABLES["refresh-tokens"]

    assert spec["KeySchema"] == [{"AttributeName": "token_hash", "KeyType": "HASH"}]
    index = spec["GlobalSecondaryIndexes"][0]
    assert index["IndexName"] == REFRESH_FAMILY_INDEX
    assert index["KeySchema"] == [
        {"AttributeName": "family_id", "KeyType": "HASH"},
        {"AttributeName": "generation", "KeyType": "RANGE"},
    ]


def test_login_attempts_ranges_on_the_timestamp_so_an_attempt_is_an_append() -> None:
    """Hash `identity_key`, range `attempted_at`.

    Without the range key a second failure would overwrite the first and the
    progressive lockout would never see a history to escalate on.
    """
    from app.db.tables import TABLES

    assert TABLES["login-attempts"]["KeySchema"] == [
        {"AttributeName": "identity_key", "KeyType": "HASH"},
        {"AttributeName": "attempted_at", "KeyType": "RANGE"},
    ]


def test_credentials_has_no_ttl_and_the_other_two_expire_on_expires_at() -> None:
    """A credential that expired on a reclaim schedule signs somebody out.

    DynamoDB deletes on its own timetable rather than on any deadline chosen
    here, so a TTL on `credentials` would be an account locked out at a moment
    nothing chose. The other two are storage reclamation for records the package
    also checks the deadline of on read.
    """
    from app.db.tables import ALL_TABLES

    ttl = dict(ALL_TABLES)

    assert ttl["credentials"] is None
    assert ttl["refresh-tokens"] == "expires_at"
    assert ttl["login-attempts"] == "expires_at"


def test_every_registered_table_is_actually_created_by_the_suite() -> None:
    """`ALL_TABLES` is what `conftest.create_all_tables` walks.

    A table registered in `TABLES` but missing from `ALL_TABLES` is a table no
    test can exercise and a `ResourceNotFoundException` the deployed stack does
    not have, which is the least useful kind of difference between the two.
    """
    import boto3

    from app.config import settings
    from app.db.tables import ALL_TABLES, TABLES

    assert {name for name, _ in ALL_TABLES} == set(TABLES)

    live = set(boto3.client("dynamodb").list_tables()["TableNames"])
    for name, _ in ALL_TABLES:
        assert f"{settings.DYNAMODB_TABLE_PREFIX}-{name}" in live


# ---------------------------------------------------------------------------
# The mount
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def private_key() -> Any:
    """One 2048-bit key for the module. A fixture rather than an import, because
    M1's is module scoped and a module scoped fixture does not cross files."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def identity_app(private_key: Any, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """The identity router built and mounted exactly as the composition root does.

    With no prefix, which is the whole of what changed in 0.10.0. The paths the
    tests below assert are therefore produced by the package's own derivation
    from `IDENTITY_ISSUER` rather than by anything this file writes down.
    """
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_RP_ID", "staging.webbpulse.com")

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))
    return app


def _post_paths(app: FastAPI) -> set[str]:
    return {
        route.path for route in app.routes if "POST" in getattr(route, "methods", set())
    }


def test_the_six_flow_routes_mount_under_the_issuer_path(
    identity_app: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/<name>` and not at the origin.

    This is the assertion that catches the 0.10.0 breaking change going in
    wrong. Passing a prefix here as 0.9.0 required would produce
    `/api/auth/api/auth/login`, which serves a 404 to the frontend and applies
    cleanly in Terraform.
    """
    assert set(FLOW_PATHS) <= _post_paths(identity_app)


def test_nothing_is_served_at_the_origin(identity_app: FastAPI) -> None:
    """No route escapes the issuer's path, in either direction.

    The `.well-known` pair is the reason this matters beyond tidiness: those two
    paths carry `authorization_type = "NONE"` at the gateway, and a copy of them
    served at the origin would be a second, ungated surface nobody declared. The
    flow routes at the origin would be state changing routes outside every route
    key in `apigateway.tf`.
    """
    served = {getattr(route, "path", "") for route in identity_app.routes}
    identity_paths = {
        path
        for path in served
        if path.startswith("/.well-known/")
        or path in {f"/{name.rsplit('/', 1)[-1]}" for name in FLOW_PATHS}
        or path == "/health"
    }

    assert identity_paths == set(), sorted(identity_paths)


def test_every_identity_route_sits_under_the_issuer_path(
    identity_app: FastAPI,
) -> None:
    """Stated positively, so a route added by a later milestone is covered too.

    FastAPI's own `/openapi.json` and `/docs` come from the bare `FastAPI()` this
    fixture builds and are not the router's, so they are excluded by name rather
    than by allowing anything outside the prefix.
    """
    from webbpulse.identity import IdentitySettings, identity_prefix

    prefix = identity_prefix(IdentitySettings())  # pyright: ignore[reportCallIssue]
    assert prefix == "/api/auth"

    framework = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    for route in identity_app.routes:
        path = getattr(route, "path", "")
        if path in framework:
            continue
        assert path.startswith(prefix), path


def test_the_documents_still_answer_where_the_authorizer_looks(
    identity_app: FastAPI,
) -> None:
    """M1's three routes survive M2's arrival.

    Mounting the flows is conditional inside the package on hooks and a
    credential store being present, and the documents are not. This is the check
    that supplying the first pair did not disturb the second.
    """
    client = TestClient(identity_app)

    assert client.get("/api/auth/.well-known/openid-configuration").status_code == 200
    assert client.get("/api/auth/.well-known/jwks.json").status_code == 200
    assert client.get("/api/auth/health").status_code == 200


def test_the_flows_do_not_mount_without_hooks_and_a_credential_store(
    identity_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The package's condition, asserted so this product knows what turns M2 on.

    If this ever passes with the flows present, the package stopped gating them
    and the identity function would serve a login route in a deployment whose
    tables do not exist yet.
    """
    import boto3
    from webbpulse.identity import IdentitySettings, build_identity_router

    from app.version import VERSION

    del identity_app  # Only here for the environment its fixture sets up.

    documents_only = FastAPI()
    documents_only.include_router(
        build_identity_router(
            IdentitySettings(),  # pyright: ignore[reportCallIssue]
            kms_client=boto3.client("kms"),
            service="webbpulse-portfolio-identity",
            version=VERSION,
        )
    )

    assert _post_paths(documents_only) & set(FLOW_PATHS) == set()
