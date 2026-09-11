"""M6: the two OAuth tables, the client id switch, the secrets and the new hook."""

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
    """Hash `state`, a string, no range key, no index."""
    from app.db.tables import TABLES

    spec = TABLES["oauth-states"]

    assert spec["KeySchema"] == [{"AttributeName": "state", "KeyType": "HASH"}]
    assert spec["AttributeDefinitions"] == [
        {"AttributeName": "state", "AttributeType": "S"}
    ]
    assert "GlobalSecondaryIndexes" not in spec


def test_the_link_table_is_keyed_on_the_provider_identity() -> None:
    """Hash `provider_subject`, a string, no range key."""
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
    """`user_id-index`, hash `user_id`, projecting ALL."""
    from webbpulse.identity import OAUTH_LINK_USER_INDEX

    from app.db.tables import TABLES

    indexes = TABLES["oauth-links"]["GlobalSecondaryIndexes"]

    assert len(indexes) == 1
    assert indexes[0]["IndexName"] == OAUTH_LINK_USER_INDEX
    assert indexes[0]["KeySchema"] == [{"AttributeName": "user_id", "KeyType": "HASH"}]
    assert indexes[0]["Projection"] == {"ProjectionType": "ALL"}


def test_the_two_oauth_tables_expire_opposite_things() -> None:
    """States expire, links never do, and both are decisions."""
    from app.db.tables import ALL_TABLES

    ttls = dict(ALL_TABLES)

    assert ttls["oauth-states"] == "expires_at"
    assert ttls["oauth-links"] is None


def test_both_oauth_tables_are_created_by_the_suite() -> None:
    """Registered in `ALL_TABLES`, which is what `conftest` walks."""
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
    """The set Terraform's `tables` map has to match, named rather than counted."""
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
    """`IDENTITY_GOOGLE_CLIENT_ID` and `IDENTITY_GITHUB_CLIENT_ID` land on the
    fields.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_GOOGLE_CLIENT_ID", GOOGLE_CLIENT_ID)
    monkeypatch.setenv("IDENTITY_GITHUB_CLIENT_ID", GITHUB_CLIENT_ID)

    settings = IdentitySettings()

    assert settings.google_client_id == GOOGLE_CLIENT_ID
    assert settings.github_client_id == GITHUB_CLIENT_ID


def test_unset_client_ids_are_empty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Which is the deployed state today, and is a valid one rather than a fault."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()

    assert settings.google_client_id == ""
    assert settings.github_client_id == ""


def test_the_redirect_uri_allow_list_is_read_as_a_json_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IDENTITY_OAUTH_REDIRECT_URIS` is JSON, not comma separated values."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_OAUTH_REDIRECT_URIS", json.dumps([REDIRECT_URI]))

    assert IdentitySettings().oauth_redirect_uris == [REDIRECT_URI]


def test_both_providers_are_enabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This product sets no `IDENTITY_OAUTH_PROVIDERS`, so the default is the list."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    assert set(IdentitySettings().oauth_providers) == {"google", "github"}


def test_the_composition_root_supplies_both_oauth_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`oauth_states` and `oauth_links` are populated, not left at their defaults."""
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
    """Each store repository carries its own table's name."""
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
    """`oauth_client_secrets` reaches `build_identity_router` as a keyword."""
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
    """No ARN configured means nothing to read, and that is a success."""
    from app.composition.identity import build_oauth_client_secrets
    from app.composition.settings import Settings

    settings = Settings(APP_SECRETS_ARN=None, app_secrets_arn="")

    assert build_oauth_client_secrets(settings) == {}


def test_only_the_providers_whose_secret_is_present_are_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One provider registered is a valid state, not a half-configured one."""
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
    """The deployed state today: a real secret that carries no OAuth key."""
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
    """The secret's keys are one convention, and this is what holds them to it."""
    from app.composition.identity import OAUTH_SECRET_KEYS

    assert OAUTH_SECRET_KEYS
    for provider, key in OAUTH_SECRET_KEYS.items():
        assert key == key.upper(), f"{provider} maps to a non upper case key: {key}"
        assert provider == provider.lower(), provider


def test_the_hooks_still_satisfy_the_packages_protocol() -> None:
    """M6 adds a hook, and this is the check that would have caught its absence."""
    from webbpulse.identity import IdentityHooks

    assert isinstance(PortfolioIdentityHooks(), IdentityHooks)


def test_the_product_reports_no_sign_in_method_the_package_cannot_see() -> None:
    """`False`, because Portfolio genuinely holds none."""
    hooks = PortfolioIdentityHooks()

    assert hooks.has_other_sign_in_method("1") is False
    assert hooks.has_other_sign_in_method("does-not-exist") is False


def test_no_oauth_route_mounts_without_a_client_id(
    identity_app_without_providers: FastAPI,
) -> None:
    """THE DEPLOYED STATE. Both stores supplied, neither client id set, no routes."""
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
    """Turning OAuth off turns nothing else off."""
    paths = _all_paths(identity_app_without_providers)

    assert "/api/auth/login" in paths
    assert "/api/auth/refresh" in paths
    assert "/api/auth/.well-known/openid-configuration" in paths


def test_the_five_oauth_routes_mount_once_a_client_id_is_set(
    identity_app_with_providers: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/oauth/...` and not at the origin."""
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
    """The deliberate opposite of the literals above."""
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
    """THE DEPLOYED STATE, and the one OAuth route that is in it."""
    assert OAUTH_PROVIDERS_PATH_FULL in _paths_for_method(
        identity_app_without_providers, "GET"
    )


def test_provider_discovery_answers_an_empty_list_when_unconfigured(
    identity_app_without_providers: FastAPI,
) -> None:
    """It answers, it answers 200, and the list is empty."""
    from fastapi.testclient import TestClient

    with TestClient(identity_app_without_providers) as client:
        response = client.get(OAUTH_PROVIDERS_PATH_FULL)

    assert response.status_code == 200
    assert response.json() == {"providers": []}


def test_provider_discovery_is_publicly_cacheable(
    identity_app_without_providers: FastAPI,
) -> None:
    """`Cache-Control: public, max-age=300`, which is why this is cheap to call."""
    from fastapi.testclient import TestClient

    with TestClient(identity_app_without_providers) as client:
        response = client.get(OAUTH_PROVIDERS_PATH_FULL)

    assert response.headers["cache-control"] == "public, max-age=300"


def test_provider_discovery_lists_nothing_without_the_client_secrets(
    identity_app_with_providers: FastAPI,
) -> None:
    """Both client ids set, no secret in the blob, and still an empty list."""
    from fastapi.testclient import TestClient

    assert "/api/auth/oauth/{provider}/start" in _paths_for_method(
        identity_app_with_providers, "GET"
    )

    with TestClient(identity_app_with_providers) as client:
        response = client.get(OAUTH_PROVIDERS_PATH_FULL)

    assert response.status_code == 200
    assert response.json() == {"providers": []}


def test_the_discovery_path_is_the_packages_own_constant() -> None:
    """The literal above against the package's constant, like the five below it."""
    from webbpulse.identity.oauth_routes import OAUTH_PROVIDERS_PATH

    assert f"/api/auth{OAUTH_PROVIDERS_PATH}" == OAUTH_PROVIDERS_PATH_FULL


def test_one_provider_is_enough_to_mount_the_routes(
    monkeypatch: pytest.MonkeyPatch, private_key: Any
) -> None:
    """Google alone mounts all five, which is the likely first state."""
    app = _build_identity_app(
        monkeypatch, private_key, google=GOOGLE_CLIENT_ID, github=""
    )

    assert "/api/auth/oauth/{provider}/start" in _paths_for_method(app, "GET")


class _Captured(Exception):
    """Unwinds `build_router` once the call it made has been captured."""


class _FakeSecretsModule:
    """Stands in for `app.secrets` so no Secrets Manager call is made."""

    def __init__(self, values: dict[str, str]) -> None:
        """Hold the values this fake secrets loader returns."""
        self._values = values

    def load_app_secrets(self, secret_arn: str, client: Any = None) -> dict[str, str]:
        """Return the held values, ignoring the ARN and client."""
        del secret_arn, client
        return dict(self._values)


def _logical_name_of(store: Any) -> str:
    """The unprefixed table a Dynamo store's repository is pointed at."""
    return str(store._repo.logical_name)


def _capture_build(
    monkeypatch: pytest.MonkeyPatch, boto3: Any, package: Any
) -> dict[str, Any]:
    """Intercept `build_identity_router` and record what the root passed it."""
    captured: dict[str, Any] = {}

    def capture(settings: Any, *args: Any, **kwargs: Any) -> Any:
        """Record the stores and keyword arguments, then abort the build."""
        captured["stores"] = args[1] if len(args) > 1 else kwargs.get("stores")
        captured["kwargs"] = kwargs
        raise _Captured

    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: object())
    monkeypatch.setattr(package, "build_identity_router", capture)
    return captured


def _identity_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `IDENTITY_*` variables `terraform/lambda_domains.tf` sets."""
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
    """The identity router as the composition root builds it, with these ids set."""
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
    """Every path the application serves for the given method."""
    return {
        route.path for route in app.routes if method in getattr(route, "methods", set())
    }


def _all_paths(app: FastAPI) -> set[str]:
    """Every path the application serves, whatever the method."""
    return {route.path for route in app.routes if hasattr(route, "path")}
