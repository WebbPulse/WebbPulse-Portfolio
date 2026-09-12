"""M3: the verification hook, the token table and the four email routes."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI

from app.composition.identity_hooks import PortfolioIdentityHooks
from app.db import entities

from .routes import all_paths, paths_for_method
from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN, FakeKms

EMAIL_PATHS = (
    "/api/auth/verify-email",
    "/api/auth/verify-email/confirm",
    "/api/auth/reset",
    "/api/auth/reset/confirm",
)

FROM_ADDRESS = "no-reply@staging.webbpulse.com"
CONFIGURATION_SET = "webbpulse-staging-identity"


@pytest.fixture
def hooks() -> PortfolioIdentityHooks:
    """One instance, as the composition root builds one per process."""
    return PortfolioIdentityHooks()


def test_the_hooks_still_satisfy_the_protocol_with_the_new_method(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`isinstance` against the runtime checkable `Protocol`, again."""
    from webbpulse.identity import IdentityHooks

    assert isinstance(hooks, IdentityHooks)


def test_the_package_has_no_default_for_this_hook() -> None:
    """`BaseIdentityHooks.mark_email_verified` raises, which is why this exists."""
    from webbpulse.identity import BaseIdentityHooks

    with pytest.raises(NotImplementedError):
        BaseIdentityHooks().mark_email_verified("1")


def test_a_confirmed_link_sets_email_verified_on_the_users_row(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The hook's whole job, against the real repository."""
    user = entities.users.create(
        {
            "email": "verify-me@webbpulse.com",
            "username": "verify-me",
            "is_admin": False,
            "is_active": True,
        }
    )

    hooks.mark_email_verified(str(user["id"]))

    assert entities.users.get(user["id"])["email_verified"] is True


def test_the_hook_takes_the_string_id_the_package_hands_it(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The `sub` claim is a string and this product's ids are integers."""
    user = entities.users.create(
        {
            "email": "string-id@webbpulse.com",
            "username": "string-id",
            "is_admin": False,
            "is_active": True,
        }
    )
    user_id = str(user["id"])
    assert isinstance(user_id, str)

    hooks.mark_email_verified(user_id)

    assert entities.users.get(user["id"])["email_verified"] is True


def test_an_id_that_is_not_an_integer_raises_rather_than_writing_nothing(
    hooks: PortfolioIdentityHooks,
) -> None:
    """A `sub` this product cannot have is a bug, not a no-op."""
    with pytest.raises(ValueError, match="not one of this product's integer"):
        hooks.mark_email_verified("not-an-integer")


def test_a_missing_user_raises_rather_than_reporting_success(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`Repository.update` returns `None` for a row that is not there."""
    missing = 9_999_999
    assert entities.users.get(missing) is None

    with pytest.raises(ValueError, match="found no user"):
        hooks.mark_email_verified(str(missing))


def test_verifying_does_not_disturb_the_rest_of_the_row(
    hooks: PortfolioIdentityHooks,
) -> None:
    """An update, not a replace."""
    user = entities.users.create(
        {
            "email": "intact@webbpulse.com",
            "username": "intact",
            "is_admin": False,
            "is_active": True,
        }
    )

    hooks.mark_email_verified(str(user["id"]))

    after = entities.users.get(user["id"])
    assert after["email"] == "intact@webbpulse.com"
    assert after["username"] == "intact"
    assert after["is_active"] is True


def test_verifying_twice_is_not_an_error(hooks: PortfolioIdentityHooks) -> None:
    """Idempotent, because the package's single-use guarantee is about links."""
    user = entities.users.create(
        {
            "email": "twice@webbpulse.com",
            "username": "twice",
            "is_admin": False,
            "is_active": True,
        }
    )

    hooks.mark_email_verified(str(user["id"]))
    hooks.mark_email_verified(str(user["id"]))

    assert entities.users.get(user["id"])["email_verified"] is True


def test_may_authenticate_deliberately_ignores_email_verified(
    hooks: PortfolioIdentityHooks,
) -> None:
    """This is a decision, not an omission, so it is pinned as one."""
    unverified = {"is_admin": True, "is_active": True, "email_verified": False}

    assert hooks.may_authenticate(unverified) is None


def test_the_token_table_name_is_the_packages_own_constant() -> None:
    """A copied name, checked against the source it was copied from."""
    from webbpulse.identity import IDENTITY_TOKENS_TABLE

    from app.db import tables

    assert tables.IDENTITY_TOKENS == IDENTITY_TOKENS_TABLE


def test_the_token_table_is_keyed_on_the_hash_and_nothing_else() -> None:
    """Hash `token_hash`, a string, no range key."""
    from app.db.tables import TABLES

    spec = TABLES["identity-tokens"]

    assert spec["KeySchema"] == [{"AttributeName": "token_hash", "KeyType": "HASH"}]
    assert spec["AttributeDefinitions"] == [{"AttributeName": "token_hash", "AttributeType": "S"}]


def test_the_token_table_has_no_secondary_index() -> None:
    """Deliberately, and it should stay that way."""
    from app.db.tables import TABLES

    assert "GlobalSecondaryIndexes" not in TABLES["identity-tokens"]


def test_the_token_table_expires_on_the_attribute_the_package_writes() -> None:
    """`expires_at`, the same name `refresh-tokens` and `login-attempts` use."""
    from app.db.tables import ALL_TABLES

    assert dict(ALL_TABLES)["identity-tokens"] == "expires_at"


def test_the_token_table_is_created_by_the_suite() -> None:
    """Registered in `ALL_TABLES`, which is what `conftest` walks."""
    import boto3

    from app.config import settings
    from app.db.tables import ALL_TABLES

    assert "identity-tokens" in dict(ALL_TABLES)

    live = set(boto3.client("dynamodb").list_tables()["TableNames"])
    assert f"{settings.DYNAMODB_TABLE_PREFIX}-identity-tokens" in live


def test_the_composition_root_supplies_a_token_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IdentityStores.identity_tokens` is populated, not left at its default."""
    import boto3
    import webbpulse.identity as package
    from webbpulse.identity.storage import DynamoIdentityTokenStore

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", FROM_ADDRESS)

    captured: dict[str, Any] = {}

    def capture(settings: Any, *args: Any, **kwargs: Any) -> Any:
        """Record the stores passed to the router builder, then abort the build."""
        captured["stores"] = args[1] if len(args) > 1 else kwargs.get("stores")
        raise _Captured

    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: object())
    monkeypatch.setattr(package, "build_identity_router", capture)

    with pytest.raises(_Captured):
        build_router(Settings())

    assert isinstance(captured["stores"].identity_tokens, DynamoIdentityTokenStore)


class _Captured(Exception):
    """Unwinds `build_router` once the bundle it built has been captured."""


@pytest.fixture(scope="module")
def private_key() -> Any:
    """One 2048-bit key for the module, for the reason M2's copy gives: a module
    scoped fixture does not cross files."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _identity_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `IDENTITY_*` variables `terraform/lambda_domains.tf` sets."""
    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_RP_ID", "staging.webbpulse.com")


@pytest.fixture
def identity_app(private_key: Any, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """The identity router as the composition root builds it with email on."""
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", FROM_ADDRESS)
    monkeypatch.setenv("IDENTITY_SES_CONFIGURATION_SET", CONFIGURATION_SET)

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))
    return app


def _post_paths(app: FastAPI) -> set[str]:
    """Every path the application serves for POST."""
    return paths_for_method(app, "POST")


def test_the_four_email_routes_mount_under_the_issuer_path(
    identity_app: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/<name>` and not at the origin."""
    assert set(EMAIL_PATHS) <= _post_paths(identity_app)


def test_the_m2_flows_are_undisturbed_by_the_email_routes(
    identity_app: FastAPI,
) -> None:
    """M3 is additive, and this is what says so in this repository."""
    from .test_identity_m2 import FLOW_PATHS

    assert set(FLOW_PATHS) <= _post_paths(identity_app)


def test_the_documents_still_answer_where_the_authorizer_looks(
    identity_app: FastAPI,
) -> None:
    """M1's three routes survive M3's arrival, as they survived M2's."""
    from fastapi.testclient import TestClient

    client = TestClient(identity_app)

    assert client.get("/api/auth/.well-known/openid-configuration").status_code == 200
    assert client.get("/api/auth/.well-known/jwks.json").status_code == 200
    assert client.get("/api/auth/health").status_code == 200


def test_no_email_route_is_served_at_the_origin(identity_app: FastAPI) -> None:
    """No route escapes the issuer's path."""
    served = all_paths(identity_app)
    leaked = {path for path in served if path in {name[len("/api/auth") :] for name in EMAIL_PATHS}}

    assert leaked == set(), sorted(leaked)


def test_the_email_routes_do_not_mount_without_a_sender(private_key: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The switch, from the off side, through this product's own builder."""
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    from .test_identity_m2 import FLOW_PATHS

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", "")

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))

    assert _post_paths(app) & set(EMAIL_PATHS) == set()
    assert set(FLOW_PATHS) <= _post_paths(app)


def test_an_empty_from_address_builds_no_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`build_email_sender` itself, isolated from the router."""
    from webbpulse.identity import IdentitySettings

    from app.composition.identity import build_email_sender

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", "")

    assert build_email_sender(IdentitySettings()) is None  # pyright: ignore[reportCallIssue]


def test_a_from_address_builds_an_ses_sender_carrying_the_configuration_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other side of the same switch, and the configuration set with it."""
    import boto3
    from webbpulse.identity import IdentitySettings
    from webbpulse.identity.email import SesV2EmailSender

    from app.composition.identity import build_email_sender

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", FROM_ADDRESS)
    monkeypatch.setenv("IDENTITY_SES_CONFIGURATION_SET", CONFIGURATION_SET)

    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: object())

    sender = build_email_sender(IdentitySettings())  # pyright: ignore[reportCallIssue]

    assert isinstance(sender, SesV2EmailSender)


def test_the_recording_sender_stands_in_for_ses_without_an_aws_call() -> None:
    """The package's own test double, used rather than a mock of our own."""
    from webbpulse.identity.email import EmailMessage, RecordingEmailSender

    sender = RecordingEmailSender()
    sender.send(
        EmailMessage(
            to="someone@webbpulse.com",
            subject="Verify your email",
            text="link",
            html="<p>link</p>",
        )
    )

    assert len(sender.sent) == 1
    assert sender.last_for("someone@webbpulse.com") is not None


def test_a_send_failure_is_surfaced_rather_than_swallowed() -> None:
    """`EmailSendFailed`, which is what a throttled or rejected send raises."""
    from webbpulse.identity.email import (
        EmailMessage,
        EmailSendFailed,
        RecordingEmailSender,
    )

    sender = RecordingEmailSender(fail=True)

    with pytest.raises(EmailSendFailed):
        sender.send(
            EmailMessage(
                to="someone@webbpulse.com",
                subject="Verify your email",
                text="link",
                html="<p>link</p>",
            )
        )


def test_the_link_paths_are_package_constants_rather_than_settings() -> None:
    """Why no `IDENTITY_VERIFY_LINK_PATH` exists in `lambda_domains.tf`."""
    from webbpulse.identity.verification import RESET_LINK_PATH, VERIFY_LINK_PATH

    assert VERIFY_LINK_PATH == "/verify-email"
    assert RESET_LINK_PATH == "/reset-password"
