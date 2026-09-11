"""M3: the verification hook, the token table and the four email routes.

Same principle as `test_identity_m1.py` and `test_identity_m2.py`. The package's
own suite already proves that a link is single use, that consuming one is
atomic, that an expired one is refused and that both request routes answer 200
for an address that does not exist. Re-asserting any of that here would pin the
package's behaviour twice and tell nobody anything about this product.

What no test in the package can cover is the three seams M3 adds here.

**`mark_email_verified`**, which is the one hook in the whole protocol with no
usable default. `BaseIdentityHooks` raises for it, deliberately, because there
is no way for a package to guess where a product keeps that flag. This
product's answer is a boolean column on the `users` row, keyed by an integer id
the package hands back as a string, and both halves of that conversion are
places a mistake is silent: `int("7")` and `users.update(7, ...)` agree, while
`users.update("7", ...)` writes nothing and returns `None`. So the hook is
exercised against the real repository on moto rather than a stub.

**The identity-tokens table**, against the constants the package exports, for
the same reason M2's three tables are checked that way. Keys copied from
`webbpulse.identity.storage` into `app/db/tables.py` and again into
`terraform/dynamodb.tf` are copies that drift, and a drifted key name is a
`ValidationException` on the first click of a mailed link rather than anything
a type checker sees.

**The conditional mount**, which is what makes M3 different in kind from M2.
M2's flows mount whenever hooks and a credential store are present, and this
product always supplies both. M3's four routes mount only when an `EmailSender`
*and* an identity-tokens store are both supplied, and this product supplies the
sender only when `IDENTITY_EMAIL_FROM` is set, which Terraform sets only when
custom domains are on. That is a real deployment shape, not a hypothetical: a
staging profile with no hosted zone gets no SES, and it should get no email
routes rather than four routes that answer 503. Both sides of that switch are
asserted below.

The `RecordingEmailSender` the package ships is used rather than a mock, so
what is asserted about a send is asserted against the same `EmailMessage` the
SES sender would have been handed.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI

from app.composition.identity_hooks import PortfolioIdentityHooks
from app.db import entities

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
    """`isinstance` against the runtime checkable `Protocol`, again.

    M2's file asserts this too, and it is worth asserting a second time here
    because M3 is the release that added a method to the protocol. A product
    that upgraded the package without implementing `mark_email_verified` would
    still pass every M2 assertion and fail on the first confirmed link.
    """
    from webbpulse.identity import IdentityHooks

    assert isinstance(hooks, IdentityHooks)


def test_the_package_has_no_default_for_this_hook() -> None:
    """`BaseIdentityHooks.mark_email_verified` raises, which is why this exists.

    Pinned so the reason this product wrote one is written down. Every other
    hook has a default the package can justify; where a product records that an
    address is verified is not something a package can guess, so it declines to.
    """
    from webbpulse.identity import BaseIdentityHooks

    with pytest.raises(NotImplementedError):
        BaseIdentityHooks().mark_email_verified("1")


def test_a_confirmed_link_sets_email_verified_on_the_users_row(
    hooks: PortfolioIdentityHooks,
) -> None:
    """The hook's whole job, against the real repository.

    `email_verified` is a new column and DynamoDB needs no migration for one,
    so every row written before M3 simply does not have it. Reading it back as
    `True` here is the assertion that the write landed on the row the package
    named rather than on a new one.
    """
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
    """The `sub` claim is a string and this product's ids are integers.

    That conversion is the single most likely thing to be wrong here, and it is
    wrong silently: `Repository.update` keys on the value it is given, so an
    unconverted `"7"` matches no item, writes nothing and returns `None`.
    Passing the id the way the package passes it is the only way to catch that.
    """
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
    """A `sub` this product cannot have is a bug, not a no-op.

    Nothing should ever produce one: `create_user` returns the counter's integer
    and `load_user_by_id` converts back. If one appears anyway the link has
    already been consumed by the time this runs, so failing loudly is what gets
    the user a new link instead of a silently unverified address.
    """
    with pytest.raises(ValueError, match="not one of this product's integer"):
        hooks.mark_email_verified("not-an-integer")


def test_a_missing_user_raises_rather_than_reporting_success(
    hooks: PortfolioIdentityHooks,
) -> None:
    """`Repository.update` returns `None` for a row that is not there.

    It does not raise, which is the specific reason this hook checks the return
    value. A deleted account whose verification link is clicked afterwards would
    otherwise consume the link, write nothing and answer 200, and the address
    would be reported verified on a row that no longer exists.
    """
    missing = 9_999_999
    assert entities.users.get(missing) is None

    with pytest.raises(ValueError, match="found no user"):
        hooks.mark_email_verified(str(missing))


def test_verifying_does_not_disturb_the_rest_of_the_row(
    hooks: PortfolioIdentityHooks,
) -> None:
    """An update, not a replace.

    Worth pinning because the hook writes a one-key mapping, and a repository
    that took that as the whole item would blank the address, the username and
    the admin flag on the account it was verifying.
    """
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
    """Idempotent, because the package's single-use guarantee is about links.

    A second *link* cannot be confirmed twice, and `LinkService` enforces that
    atomically. Two different links for the same address both confirming is a
    normal thing for a user to cause by requesting a new one and then finding
    the old mail, and it should not be an error.
    """
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
    """This is a decision, not an omission, so it is pinned as one.

    Gating sign-in on `email_verified` would lock out the seeded administrator,
    whose row predates the column and who has no mailbox flow to fix it with. It
    would also make the legacy `/api/v1/admin/login` and the M2 `/api/auth/login`
    disagree about the same account while both are live, which is the worst
    possible state for a half-migrated auth surface to be in.

    If this test ever needs to change, the seeded administrator needs a verified
    address first.
    """
    unverified = {"is_admin": True, "is_active": True, "email_verified": False}

    assert hooks.may_authenticate(unverified) is None


def test_the_token_table_name_is_the_packages_own_constant() -> None:
    """A copied name, checked against the source it was copied from."""
    from webbpulse.identity import IDENTITY_TOKENS_TABLE

    from app.db import tables

    assert tables.IDENTITY_TOKENS == IDENTITY_TOKENS_TABLE


def test_the_token_table_is_keyed_on_the_hash_and_nothing_else() -> None:
    """Hash `token_hash`, a string, no range key.

    `DynamoIdentityTokenStore` builds exactly this key for both the write at
    issue time and the conditional update that consumes the link, and a range
    key would make the consume a query rather than the single atomic update the
    single-use guarantee rests on.
    """
    from app.db.tables import TABLES

    spec = TABLES["identity-tokens"]

    assert spec["KeySchema"] == [{"AttributeName": "token_hash", "KeyType": "HASH"}]
    assert spec["AttributeDefinitions"] == [
        {"AttributeName": "token_hash", "AttributeType": "S"}
    ]


def test_the_token_table_has_no_secondary_index() -> None:
    """Deliberately, and it should stay that way.

    `DynamoIdentityTokenStore.revoke_for_user` raises rather than scanning, and
    the package's M3 decision 6 explains why: a user index would cost a write on
    the click path to serve the issue path, and what it would buy is closing a
    link the user asked for that expires on its own inside an hour.
    """
    from app.db.tables import TABLES

    assert "GlobalSecondaryIndexes" not in TABLES["identity-tokens"]


def test_the_token_table_expires_on_the_attribute_the_package_writes() -> None:
    """`expires_at`, the same name `refresh-tokens` and `login-attempts` use.

    Not `ttl`, which is the `meta` table's name. Both names exist in this
    configuration and DynamoDB silently never expires anything when the TTL is
    enabled on an attribute no item carries.

    The TTL is storage reclamation and never the expiry check: DynamoDB deletes
    on its own schedule, typically within a couple of days, and `confirm`
    re-checks the deadline against the clock every time.
    """
    from app.db.tables import ALL_TABLES

    assert dict(ALL_TABLES)["identity-tokens"] == "expires_at"


def test_the_token_table_is_created_by_the_suite() -> None:
    """Registered in `ALL_TABLES`, which is what `conftest` walks.

    A table in `TABLES` but not in `ALL_TABLES` is one no test can exercise and
    a `ResourceNotFoundException` the deployed stack does not have.
    """
    import boto3

    from app.config import settings
    from app.db.tables import ALL_TABLES

    assert "identity-tokens" in dict(ALL_TABLES)

    live = set(boto3.client("dynamodb").list_tables()["TableNames"])
    assert f"{settings.DYNAMODB_TABLE_PREFIX}-identity-tokens" in live


def test_the_composition_root_supplies_a_token_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IdentityStores.identity_tokens` is populated, not left at its default.

    It defaults to `None`, and `email_enabled` on the package's flow description
    is true only when a sender *and* this store are both present. A bundle
    missing it would silently unmount the four routes while every other identity
    route kept working, which is the quietest possible way for M3 to be off.

    Asserted by intercepting the bundle the composition root actually builds,
    rather than by rebuilding one here, so it is this product's wiring under
    test and not a copy of it.
    """
    import boto3
    import webbpulse.identity as package
    from webbpulse.identity.storage import DynamoIdentityTokenStore

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", FROM_ADDRESS)

    captured: dict[str, Any] = {}

    def capture(settings: Any, *args: Any, **kwargs: Any) -> Any:
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
    """The identity router as the composition root builds it with email on.

    `IDENTITY_EMAIL_FROM` set is the whole switch: `build_email_sender` reads it,
    returns a `SesV2EmailSender` when it is non-empty and `None` when it is not,
    and `build_identity_router` mounts the four routes only when it is handed a
    sender. The `boto3.client` monkeypatch covers `sesv2` as well as `kms`, so
    no AWS call is made for either.
    """
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
    return {
        route.path for route in app.routes if "POST" in getattr(route, "methods", set())
    }


def test_the_four_email_routes_mount_under_the_issuer_path(
    identity_app: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/<name>` and not at the origin.

    The same assertion M2 makes about its six, for the same reason: the paths
    come from the package's derivation from `IDENTITY_ISSUER` rather than from
    anything this file or the composition root writes down.
    """
    assert set(EMAIL_PATHS) <= _post_paths(identity_app)


def test_the_m2_flows_are_undisturbed_by_the_email_routes(
    identity_app: FastAPI,
) -> None:
    """M3 is additive, and this is what says so in this repository.

    The package's changelog says the release is additive. That is a claim about
    the package; whether *this* composition root passing a fifth and sixth
    argument left the first four alone is a claim about this file.
    """
    from .test_identity_m2 import FLOW_PATHS

    assert set(FLOW_PATHS) <= _post_paths(identity_app)


def test_the_documents_still_answer_where_the_authorizer_looks(
    identity_app: FastAPI,
) -> None:
    """M1's three routes survive M3's arrival, as they survived M2's.

    API Gateway fetches the discovery document at `CreateAuthorizer` time, so
    these two are load bearing for an apply rather than only for a caller.
    """
    from fastapi.testclient import TestClient

    client = TestClient(identity_app)

    assert client.get("/api/auth/.well-known/openid-configuration").status_code == 200
    assert client.get("/api/auth/.well-known/jwks.json").status_code == 200
    assert client.get("/api/auth/health").status_code == 200


def test_no_email_route_is_served_at_the_origin(identity_app: FastAPI) -> None:
    """No route escapes the issuer's path.

    A copy of `/reset/confirm` at the origin would be a password-setting route
    outside every route key in `apigateway.tf`, which in a deployment with a
    `$default` integration would be reachable and gated by nothing.
    """
    served = {getattr(route, "path", "") for route in identity_app.routes}
    leaked = {
        path
        for path in served
        if path in {name[len("/api/auth") :] for name in EMAIL_PATHS}
    }

    assert leaked == set(), sorted(leaked)


def test_the_email_routes_do_not_mount_without_a_sender(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch, from the off side, through this product's own builder.

    An empty `IDENTITY_EMAIL_FROM` is what Terraform sets when custom domains
    are off, because without a hosted zone there is nowhere to write the DKIM
    records and the SES identity would never verify. A deployment in that shape
    should declare no route it cannot honour, rather than four routes that fail
    on every send.

    M2's six must still be there. Email being off is not identity being off.
    """
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
    """`build_email_sender` itself, isolated from the router.

    Asserted directly as well as through the mount, because this function is the
    only place in this repository that decides whether email is on, and the
    Terraform side of that decision is two `local`s in `identity.tf` that no
    Python test can read.
    """
    from webbpulse.identity import IdentitySettings

    from app.composition.identity import build_email_sender

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_EMAIL_FROM", "")

    assert build_email_sender(IdentitySettings()) is None  # pyright: ignore[reportCallIssue]


def test_a_from_address_builds_an_ses_sender_carrying_the_configuration_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other side of the same switch, and the configuration set with it.

    The configuration set is not optional in practice even though the package
    treats it as optional: `SendEmail` naming a set that does not exist is a
    hard failure on every send, and `terraform/ses.tf` creates one precisely so
    that the name passed here is always a name that resolves. Bounce and
    complaint metrics are published per configuration set, so this is also what
    makes the sending reputation visible at all.
    """
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
    """The package's own test double, used rather than a mock of our own.

    A hand written mock would assert against a shape this repository invented.
    `RecordingEmailSender` implements the same `EmailSender` interface
    `SesV2EmailSender` does, so what is captured is the `EmailMessage` the SES
    sender would have been handed, including both the text and the HTML part.
    """
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
    """`EmailSendFailed`, which is what a throttled or rejected send raises.

    Pinned because it is the exception this product's identity function will
    actually meet first: both accounts start in the SES sandbox, where SES
    refuses to deliver to any address that is not itself verified. Until the
    sandbox is left, every send to a real recipient fails this way, and it
    failing loudly is what makes that diagnosable from a log line.
    """
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
    """Why no `IDENTITY_VERIFY_LINK_PATH` exists in `lambda_domains.tf`.

    The mailed link is `<IDENTITY_FRONTEND_BASE_URL><PATH>?token=...`, and only
    the base URL is configurable. `VERIFY_LINK_PATH` and `RESET_LINK_PATH` are
    module constants in `webbpulse.identity.verification`, so the frontend has
    to serve these two paths rather than choosing them.

    This is pinned because the natural assumption is the opposite one, and
    because the frontend routes that answer these paths do not exist yet: the
    identity cutover is still behind `VITE_AUTH_MODE`.
    """
    from webbpulse.identity.verification import RESET_LINK_PATH, VERIFY_LINK_PATH

    assert VERIFY_LINK_PATH == "/verify-email"
    assert RESET_LINK_PATH == "/reset-password"
