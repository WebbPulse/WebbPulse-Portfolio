"""M5: the two passkey tables, the two flags, the origins and the mount."""

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
    """Hash `user_id`, range `credential_id`, which is the direction that matters."""
    from app.db.tables import TABLES

    spec = TABLES["passkeys"]
    assert spec["KeySchema"] == [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "credential_id", "KeyType": "RANGE"},
    ]


def test_the_passkey_table_carries_the_credential_index_the_package_names() -> None:
    """The login lookup's index, by the package's own literal, projecting ALL."""
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
    """The challenge expires; the passkey must never."""
    from app.db.tables import ALL_TABLES, IDENTITY_TTL_ATTRIBUTE

    ttls = dict(ALL_TABLES)
    assert ttls["webauthn-challenges"] == IDENTITY_TTL_ATTRIBUTE
    assert ttls["passkeys"] is None


def test_both_passkey_tables_are_created_by_the_suite(aws_tables: Any) -> None:
    """A table the package writes to that the suite does not create is a suite that
    cannot exercise a single M5 flow.
    """
    del aws_tables

    from app.db.tables import ALL_TABLES

    names = {name for name, _ in ALL_TABLES}
    assert {"passkeys", "webauthn-challenges"} <= names


def test_the_package_defaults_both_passkey_flags_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE PACKAGE SHIPS THESE ON AND THIS PRODUCT SHIPS THEM OFF."""
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
    """Terraform renders `tostring(var...)`, and pydantic reads that back."""
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
    """A list field, so the environment form is JSON and never bare CSV."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.webauthn_origins == [WEBAUTHN_ORIGIN]


def test_the_origin_is_an_origin_and_not_a_url_with_a_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheme, host and optional port only, which is what a browser sends."""
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
    """`IDENTITY_RP_ID` comes from the module, and is what the origin sits under."""
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
    """A display string, and the one M5 is the first milestone to actually read."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.rp_name == RP_NAME


def test_the_composition_root_supplies_both_passkey_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both stores, unconditionally, whatever the flag says."""
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
    assert _logical_name_of(stores.passkeys) == "passkeys"
    assert _logical_name_of(stores.webauthn_challenges) == "webauthn-challenges"


def test_the_hooks_still_satisfy_the_packages_protocol() -> None:
    """M5 adds no hook, so this has to keep passing untouched."""
    from webbpulse.identity import IdentityHooks

    from app.composition.identity_hooks import PortfolioIdentityHooks

    assert isinstance(PortfolioIdentityHooks(), IdentityHooks)


def test_no_passkey_route_mounts_with_the_flag_off(
    identity_app_passkeys_off: FastAPI,
) -> None:
    """What staging and production serve today: none of the seven."""
    assert ALL_PASSKEY_PATHS & _all_paths(identity_app_passkeys_off) == set()


def test_the_other_identity_routes_still_mount_with_the_flag_off(
    identity_app_passkeys_off: FastAPI,
) -> None:
    """The M5 bump changes the served API not at all, which is the deploy claim."""
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
    """Flipping one environment variable is the whole of the switch."""
    app = identity_app_passkeys_on

    assert set(PASSKEY_MANAGEMENT_POST_PATHS) <= _paths_for_method(app, "POST")
    assert set(PASSKEY_LOGIN_POST_PATHS) <= _paths_for_method(app, "POST")
    assert set(PASSKEY_MANAGEMENT_GET_PATHS) <= _paths_for_method(app, "GET")
    assert set(PASSKEY_MANAGEMENT_PATCH_PATHS) <= _paths_for_method(app, "PATCH")
    assert set(PASSKEY_MANAGEMENT_DELETE_PATHS) <= _paths_for_method(app, "DELETE")


def test_the_mounted_paths_are_the_packages_own_constants(
    identity_app_passkeys_on: FastAPI,
) -> None:
    """The literals at the top of this file are checked against the package."""
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
    """Turning passkeys on does not turn passwordless on with it."""
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_PASSKEYS_ENABLED", "true")

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]

    assert settings.passkeys_enabled is True
    assert settings.passkeys_passwordless is False


def test_registration_options_round_trip_against_the_in_memory_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One real ceremony leg, with this product's settings and fake stores."""
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
    """An empty origin list raises naming the variable, and does not mean "any"."""
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
    """The other half of the test above: the deployed value is accepted and used."""
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
    """The `IDENTITY_*` variables `terraform/lambda_domains.tf` sets, M5 included."""
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
    """The identity router as the composition root builds it, at this flag value."""
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
    """Every path the application serves for the given method."""
    return {
        route.path for route in app.routes if method in getattr(route, "methods", set())
    }


def _all_paths(app: FastAPI) -> set[str]:
    """Every path the application serves, whatever the method."""
    return {route.path for route in app.routes if hasattr(route, "path")}
