"""M2: the hooks, the tables and the six flow routes, as this product wires them."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from webbpulse.testing import FakeKms

from app.common.db import entities
from app.domains.identity.identity_hooks import (
    ADMIN_ROLE,
    REFUSAL_CODE,
    PortfolioIdentityHooks,
)

from ...routes import all_paths, paths_for_method
from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN

FLOW_PATHS = (
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/password",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/logout-all",
)


@pytest.fixture
def hooks() -> PortfolioIdentityHooks:
    """One instance, as the composition root builds one per process."""
    return PortfolioIdentityHooks()


def test_the_hooks_satisfy_the_protocol_structurally(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`isinstance` against the runtime checkable `Protocol`."""
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
def test_anything_but_an_active_administrator_is_refused(hooks: PortfolioIdentityHooks, user: dict[str, Any]) -> None:
    """Section 8.2: this product's policy is `is_admin` and `is_active`, both."""
    from webbpulse.identity import AuthenticationRefused

    with pytest.raises(AuthenticationRefused) as raised:
        hooks.may_authenticate(user)

    assert raised.value.error_code == REFUSAL_CODE


def test_every_refusal_carries_the_same_message(
    hooks: PortfolioIdentityHooks,
) -> None:
    """Section 5.4: a refusal must not say which column failed."""
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
    """No username, no email, no registered claims."""
    claims = hooks.claims_for({"id": 1, "username": "admin", "email": "a@b.com"})

    assert dict(claims) == {"roles": [ADMIN_ROLE]}


def test_load_user_by_id_converts_the_string_sub_to_this_products_integer_id(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`sub` is a string and Portfolio's ids are integers from the counter."""
    created = entities.users.create({"username": "someone", "email": "someone@webbpulse.com", "is_admin": True})

    loaded = hooks.load_user_by_id(str(created["id"]))

    assert loaded is not None
    assert loaded["id"] == created["id"]


@pytest.mark.parametrize("sub", ["", "not-an-integer", "1.5", "99999"])
def test_load_user_by_id_answers_none_rather_than_raising(hooks: PortfolioIdentityHooks, sub: str) -> None:
    """A `sub` this product did not mint is "no such user", not a 500."""
    assert hooks.load_user_by_id(sub) is None


def test_load_user_by_email_finds_a_lowercase_address(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The ordinary case: the row was stored lowercase and the package sends
    lowercase, so the exact pointer lookup matches."""
    created = entities.users.create({"username": "lower", "email": "lower@webbpulse.com"})

    found = hooks.load_user_by_email("lower@webbpulse.com")

    assert found is not None
    assert found["id"] == created["id"]


def test_load_user_by_email_does_not_find_a_mixed_case_row(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The known gap, asserted rather than left to be discovered."""
    entities.users.create({"username": "mixed", "email": "Mixed@WebbPulse.com"})

    assert hooks.load_user_by_email("mixed@webbpulse.com") is None


def test_load_user_by_email_answers_none_for_an_address_with_no_account(
    hooks: PortfolioIdentityHooks,
) -> None:
    """An address with no account loads as None."""
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
    """The correct answer for a product with exactly one administrator."""
    from webbpulse.identity import AuthenticationRefused

    user = hooks.create_user(email="new@webbpulse.com", attributes={})

    assert user["is_admin"] is False
    with pytest.raises(AuthenticationRefused):
        hooks.may_authenticate(user)


def test_on_user_created_promotes_an_ephemeral_e2e_user_to_administrator(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`may_authenticate` admits only administrators, so an e2e run needs the flag."""
    from webbpulse.identity.flows import EPHEMERAL_VIA

    user = hooks.create_user(email="e2e-run-gw0@e2e.invalid", attributes={"email_verified": True})
    hooks.on_user_created(user, EPHEMERAL_VIA)

    promoted = hooks.load_user_by_id(str(user["id"]))
    assert promoted is not None
    assert promoted["is_admin"] is True
    assert hooks.may_authenticate(promoted) is None


def test_on_user_created_leaves_every_other_via_a_non_administrator(
    hooks: PortfolioIdentityHooks,
) -> None:
    """Registration must not become a way to mint an administrator."""
    user = hooks.create_user(email="new@webbpulse.com", attributes={})
    hooks.on_user_created(user, "register")

    unchanged = hooks.load_user_by_id(str(user["id"]))
    assert unchanged is not None
    assert unchanged["is_admin"] is False


def test_delete_user_removes_the_row_and_reports_that_it_was_there(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The whole of an ephemeral run's cleanup, with the stream purging the rest."""
    user = hooks.create_user(email="e2e-run-gw0@e2e.invalid", attributes={})

    assert hooks.delete_user(str(user["id"])) is True
    assert hooks.load_user_by_id(str(user["id"])) is None


def test_delete_user_answers_false_for_a_row_that_is_already_gone(
    hooks: PortfolioIdentityHooks,
) -> None:
    """So a retried cleanup is not an error."""
    user = hooks.create_user(email="e2e-run-gw0@e2e.invalid", attributes={})
    hooks.delete_user(str(user["id"]))

    assert hooks.delete_user(str(user["id"])) is False


@pytest.mark.parametrize("user_id", ["", "not-an-id", "abc"])
def test_delete_user_answers_false_rather_than_raising_on_a_foreign_id(
    hooks: PortfolioIdentityHooks,
    user_id: str,
) -> None:
    """A `sub` that is not one of this product's integer ids names no row."""
    assert hooks.delete_user(user_id) is False


def test_delete_user_releases_the_address_for_the_next_run(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`create_ephemeral_user` refuses a taken address, so the unique claim must go."""
    first = hooks.create_user(email="e2e-run-gw0@e2e.invalid", attributes={})
    hooks.delete_user(str(first["id"]))

    second = hooks.create_user(email="e2e-run-gw0@e2e.invalid", attributes={})

    assert second["id"] != first["id"]
    assert hooks.load_user_by_email("e2e-run-gw0@e2e.invalid") is not None


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
    """The password lives in `credentials`, which the package writes next."""
    user = hooks.create_user(email="new@webbpulse.com", attributes={"hashed_password": "injected"})

    assert "hashed_password" not in user


def test_create_user_suffixes_a_username_that_is_already_taken(
    hooks: PortfolioIdentityHooks,
) -> None:
    """Portfolio requires a unique username and the package has no concept of one."""
    entities.users.create({"username": "taken", "email": "taken@elsewhere.com"})

    user = hooks.create_user(email="taken@webbpulse.com", attributes={})

    assert user["username"] == "taken2"


def test_create_user_ignores_an_id_supplied_through_attributes(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The counter allocates ids, and nothing reaching this hook may choose one."""
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
    """No M2 flow calls this, and the protocol types it `object`."""
    assert hooks.user_repository() is entities.users


def test_the_table_names_are_the_packages_own_constants() -> None:
    """Copied names, checked against the source they were copied from."""
    from webbpulse.identity import (
        CREDENTIALS_TABLE,
        LOGIN_ATTEMPTS_TABLE,
        REFRESH_TOKENS_TABLE,
    )

    from app.common.db import tables

    assert tables.CREDENTIALS == CREDENTIALS_TABLE
    assert tables.REFRESH_TOKENS == REFRESH_TOKENS_TABLE
    assert tables.LOGIN_ATTEMPTS == LOGIN_ATTEMPTS_TABLE


def test_credentials_is_keyed_the_way_the_store_reads_it() -> None:
    """Hash `user_id`, range `credential_type`, both strings."""
    from app.common.db.tables import TABLES

    spec = TABLES["credentials"]

    assert spec["KeySchema"] == [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "credential_type", "KeyType": "RANGE"},
    ]
    types = {attribute["AttributeName"]: attribute["AttributeType"] for attribute in spec["AttributeDefinitions"]}
    assert types == {"user_id": "S", "credential_type": "S"}


def test_refresh_tokens_carries_the_family_index_under_the_packages_name() -> None:
    """DynamoDB resolves an index by name, so the two cannot differ."""
    from webbpulse.identity import REFRESH_FAMILY_INDEX

    from app.common.db.tables import TABLES

    spec = TABLES["refresh-tokens"]

    assert spec["KeySchema"] == [{"AttributeName": "token_hash", "KeyType": "HASH"}]
    index = spec["GlobalSecondaryIndexes"][0]
    assert index["IndexName"] == REFRESH_FAMILY_INDEX
    assert index["KeySchema"] == [
        {"AttributeName": "family_id", "KeyType": "HASH"},
        {"AttributeName": "generation", "KeyType": "RANGE"},
    ]


def test_login_attempts_ranges_on_the_timestamp_so_an_attempt_is_an_append() -> None:
    """Hash `identity_key`, range `attempted_at`."""
    from app.common.db.tables import TABLES

    assert TABLES["login-attempts"]["KeySchema"] == [
        {"AttributeName": "identity_key", "KeyType": "HASH"},
        {"AttributeName": "attempted_at", "KeyType": "RANGE"},
    ]


def test_credentials_has_no_ttl_and_the_other_two_expire_on_expires_at() -> None:
    """A credential that expired on a reclaim schedule signs somebody out."""
    from app.common.db.tables import ALL_TABLES

    ttl = dict(ALL_TABLES)

    assert ttl["credentials"] is None
    assert ttl["refresh-tokens"] == "expires_at"
    assert ttl["login-attempts"] == "expires_at"


def test_every_registered_table_is_actually_created_by_the_suite() -> None:
    """`ALL_TABLES` is what `conftest.create_all_tables` walks."""
    import boto3

    from app.common.config import settings
    from app.common.db.tables import ALL_TABLES, TABLES

    assert {name for name, _ in ALL_TABLES} == set(TABLES)

    live = set(boto3.client("dynamodb").list_tables()["TableNames"])
    for name, _ in ALL_TABLES:
        assert f"{settings.DYNAMODB_TABLE_PREFIX}-{name}" in live


@pytest.fixture
def identity_app(rsa_key: Any, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """The identity router built and mounted exactly as the composition root does."""
    import boto3

    from app.common.composition.settings import Settings
    from app.domains.identity.package_glue import build_router

    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_RP_ID", "staging.webbpulse.com")

    fake = FakeKms(rsa_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))
    return app


def _post_paths(app: FastAPI) -> set[str]:
    """Every path the application serves for POST."""
    return paths_for_method(app, "POST")


def test_the_six_flow_routes_mount_under_the_issuer_path(
    identity_app: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/<name>` and not at the origin."""
    assert set(FLOW_PATHS) <= _post_paths(identity_app)


def test_nothing_is_served_at_the_origin(identity_app: FastAPI) -> None:
    """No route escapes the issuer's path, in either direction."""
    served = all_paths(identity_app)
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

    The purge route is the one exception: the Lambda Web Adapter posts a stream
    invocation to its own pass-through path, which is absolute and outside the
    issuer prefix, so that route has to sit at the root to be reachable at all.
    """
    from webbpulse.identity import IdentitySettings, identity_prefix
    from webbpulse.identity.events import events_path

    prefix = identity_prefix(IdentitySettings())  # pyright: ignore[reportCallIssue]
    assert prefix == "/api/auth"

    framework = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    allowed_outside_prefix = framework | {events_path()}
    for path in all_paths(identity_app):
        if path in allowed_outside_prefix:
            continue
        assert path.startswith(prefix), path


def test_the_documents_still_answer_where_the_authorizer_looks(
    identity_app: FastAPI,
) -> None:
    """M1's three routes survive M2's arrival."""
    client = TestClient(identity_app)

    assert client.get("/api/auth/.well-known/openid-configuration").status_code == 200
    assert client.get("/api/auth/.well-known/jwks.json").status_code == 200
    assert client.get("/api/auth/health").status_code == 200


def test_the_flows_do_not_mount_without_hooks_and_a_credential_store(
    identity_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The package's condition, asserted so this product knows what turns M2 on."""
    import boto3
    from webbpulse.identity import IdentitySettings, build_identity_router

    from app.common.version import VERSION

    del identity_app

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
