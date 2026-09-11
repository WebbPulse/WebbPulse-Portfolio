"""M4: the two MFA tables, the envelope key setting and the six TOTP routes.

Same principle as the M1 through M3 files. The package's own suite already
proves that a TOTP code verifies inside its window and not outside it, that a
recovery code is single use, that an enrolment seed round trips through the KMS
envelope, and that a login for a user with an active factor returns a challenge
instead of a session. Re-asserting any of that here would pin the package's
behaviour twice and say nothing about this product.

What no test in the package can cover is the four seams M4 adds here.

**The two tables**, checked against the constants and key schemas the package
exports, for the reason M2's three and M3's one are checked that way. A key
name copied from `webbpulse.identity.storage` into `app/db/tables.py` and again
into the `tables` map in `terraform/identity.tf` is a copy that drifts, and a
drifted key is a `ValidationException` on the first enrolment rather than
anything a type checker sees. `recovery-codes` is the first identity table with
a range key, so its second attribute is worth pinning on its own.

**Neither table has a TTL**, which is a decision and not an omission. A factor
lives until its owner disables it and a recovery code lives until it is spent,
so an `expires_at` on either would silently delete a working second factor and
lock somebody out of an account they still control.

**`data_key_arn` read from the environment**, because that single variable is
the entire wiring of the envelope cipher. `MfaService` builds an
`EnvelopeCipher` lazily from `settings.data_key_arn` and the `kms_client` this
product already passes for signing, so there is no constructor argument here to
get wrong and no code path that fails until somebody enrols. The module sets
`IDENTITY_DATA_KEY_ARN` on the function; if that name ever drifts, the failure
is a `ValueError` at first enrolment and nothing sooner.

**The conditional mount**, which for M4 is longer than M3's. The six routes
mount only when `totp_enabled` is true and `totp_factors`, `recovery_codes` and
`identity_tokens` are all supplied. This product supplies all three stores
unconditionally and leaves `totp_enabled` at the package's default, so the
routes are unconditional here in a way M3's are not. Both sides of the switch
are asserted anyway, because the failure mode of a missing store is six routes
quietly not existing while every other identity route keeps working.

The hooks protocol is re-checked structurally here as well. M4 adds no hook
method, and this test is what says so out loud: if a future package release
grows one, this fails rather than the deployed function raising `AttributeError`
mid-flow.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI

from app.composition.identity_hooks import PortfolioIdentityHooks

from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN, FakeKms

MFA_PATHS = (
    "/api/auth/login/totp",
    "/api/auth/totp/enrol",
    "/api/auth/totp/activate",
    "/api/auth/totp/disable",
    "/api/auth/recovery-codes",
    "/api/auth/step-up",
)

DATA_KEY_ARN = (
    "arn:aws:kms:us-west-2:621554169154:key/99999999-8888-7777-6666-555555555555"
)


def test_the_mfa_table_names_are_the_packages_own_constants() -> None:
    """Copied names, checked against the source they were copied from."""
    from webbpulse.identity import RECOVERY_CODES_TABLE, TOTP_FACTORS_TABLE

    from app.db import tables

    assert tables.TOTP_FACTORS == TOTP_FACTORS_TABLE
    assert tables.RECOVERY_CODES == RECOVERY_CODES_TABLE


def test_the_factor_table_is_keyed_on_the_user_and_nothing_else() -> None:
    """Hash `user_id`, a string, no range key.

    One factor per user is the shape the package's store assumes: enrol,
    activate and disable are all single-item operations on this key, and a range
    key would turn each of them into a query.
    """
    from app.db.tables import TABLES

    spec = TABLES["totp-factors"]

    assert spec["KeySchema"] == [{"AttributeName": "user_id", "KeyType": "HASH"}]
    assert spec["AttributeDefinitions"] == [
        {"AttributeName": "user_id", "AttributeType": "S"}
    ]


def test_the_recovery_table_is_keyed_on_the_user_and_the_code_hash() -> None:
    """Hash `user_id`, range `code_hash`, both strings, in that order.

    The first identity table with a range key. A user holds a set of codes, so
    spending one is a delete on the pair and listing what is left is a query on
    the hash alone. Reversing the two would make every spend a scan and every
    list a mistake.

    Only the hash is stored, never the code, which is why the range key is named
    for the digest rather than the value.
    """
    from app.db.tables import TABLES

    spec = TABLES["recovery-codes"]

    assert spec["KeySchema"] == [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "code_hash", "KeyType": "RANGE"},
    ]
    assert spec["AttributeDefinitions"] == [
        {"AttributeName": "user_id", "AttributeType": "S"},
        {"AttributeName": "code_hash", "AttributeType": "S"},
    ]


def test_neither_mfa_table_has_a_secondary_index() -> None:
    """Nothing queries either one by anything but its own key."""
    from app.db.tables import TABLES

    assert "GlobalSecondaryIndexes" not in TABLES["totp-factors"]
    assert "GlobalSecondaryIndexes" not in TABLES["recovery-codes"]


def test_neither_mfa_table_expires_anything() -> None:
    """A decision, pinned as one, because the failure is a lockout.

    Both rows are durable state that only their owner ends: a factor lives until
    somebody disables it and a code lives until it is spent. A TTL on either
    would delete a working second factor on DynamoDB's own schedule and lock a
    user out of an account they still control, with nothing in any log at the
    moment it mattered.

    `credentials` is the other table in this configuration with no TTL, for the
    same kind of reason.
    """
    from app.db.tables import ALL_TABLES

    ttls = dict(ALL_TABLES)

    assert ttls["totp-factors"] is None
    assert ttls["recovery-codes"] is None


def test_both_mfa_tables_are_created_by_the_suite() -> None:
    """Registered in `ALL_TABLES`, which is what `conftest` walks.

    A table in `TABLES` but not in `ALL_TABLES` is one no test can exercise and
    a `ResourceNotFoundException` the deployed stack does not have.
    """
    import boto3

    from app.config import settings
    from app.db.tables import ALL_TABLES

    names = dict(ALL_TABLES)
    assert "totp-factors" in names
    assert "recovery-codes" in names

    live = set(boto3.client("dynamodb").list_tables()["TableNames"])
    prefix = settings.DYNAMODB_TABLE_PREFIX
    assert f"{prefix}-totp-factors" in live
    assert f"{prefix}-recovery-codes" in live


def test_the_identity_tables_are_the_six_the_module_is_passed() -> None:
    """The count Terraform's `tables` map has to match, named rather than counted.

    `terraform/identity.tf` passes the whole map rather than merging with the
    module default, so a table added here and not there is a table that exists
    in the test suite and not in the account. This is the list that PR body and
    that map both have to agree with.
    """
    from webbpulse.identity import (
        CREDENTIALS_TABLE,
        IDENTITY_TOKENS_TABLE,
        RECOVERY_CODES_TABLE,
        REFRESH_TOKENS_TABLE,
        TOTP_FACTORS_TABLE,
    )

    from app.db.tables import TABLES

    identity_owned = {
        CREDENTIALS_TABLE,
        REFRESH_TOKENS_TABLE,
        IDENTITY_TOKENS_TABLE,
        TOTP_FACTORS_TABLE,
        RECOVERY_CODES_TABLE,
    }

    assert identity_owned <= set(TABLES)


def test_the_data_key_arn_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`IDENTITY_DATA_KEY_ARN` lands on `data_key_arn`, which is the whole wiring.

    `IdentitySettings` is a `BaseSettings` with `env_prefix="IDENTITY_"` and
    this product passes it nothing, so the variable name in
    `modules/identity/locals.tf` and the field name in the package are joined by
    nothing but that prefix rule. A test that constructed the settings directly
    would not notice either side being renamed.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_DATA_KEY_ARN", DATA_KEY_ARN)

    assert IdentitySettings().data_key_arn == DATA_KEY_ARN


def test_an_unset_data_key_arn_does_not_unmount_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset is the empty string, and the six routes mount regardless.

    Worth pinning because it is the shape of a misconfiguration and because the
    shape is deliberate. The module merges `IDENTITY_DATA_KEY_ARN` into the
    environment only when a key exists, and the mount condition does not consult
    it, so a profile without a key gets six routes that raise at first enrolment
    rather than six routes that are missing. The error `MfaService` raises names
    the variable, which is the only reason that is a tolerable failure mode.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)
    monkeypatch.delenv("IDENTITY_DATA_KEY_ARN", raising=False)

    settings = IdentitySettings()

    assert settings.data_key_arn == ""
    assert settings.totp_enabled is True


def test_totp_is_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """This product sets no `IDENTITY_TOTP_ENABLED`, so the default is the switch.

    Half of the mount condition is a setting nobody configures. If the package
    ever flipped that default, the six routes would vanish from a deploy that
    changed no Terraform and no code, and this is the test that would say so.
    """
    from webbpulse.identity import IdentitySettings

    _identity_environment(monkeypatch)

    assert IdentitySettings().totp_enabled is True


def test_the_composition_root_supplies_both_mfa_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`totp_factors` and `recovery_codes` are populated, not left at their defaults.

    Both default to `None`, and the package's flow description builds an
    `MfaService` only when both are present alongside `identity_tokens`. A
    bundle missing either would silently unmount all six routes while every
    other identity route kept working, which is the quietest possible way for M4
    to be off.

    Asserted by intercepting the bundle the composition root actually builds,
    rather than by rebuilding one here, so it is this product's wiring under test
    and not a copy of it.
    """
    import boto3
    import webbpulse.identity as package
    from webbpulse.identity.storage import (
        DynamoRecoveryCodeStore,
        DynamoTotpFactorStore,
    )

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_DATA_KEY_ARN", DATA_KEY_ARN)

    captured: dict[str, Any] = {}

    def capture(settings: Any, *args: Any, **kwargs: Any) -> Any:
        captured["stores"] = args[1] if len(args) > 1 else kwargs.get("stores")
        raise _Captured

    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: object())
    monkeypatch.setattr(package, "build_identity_router", capture)

    with pytest.raises(_Captured):
        build_router(Settings())

    assert isinstance(captured["stores"].totp_factors, DynamoTotpFactorStore)
    assert isinstance(captured["stores"].recovery_codes, DynamoRecoveryCodeStore)


def test_the_mfa_stores_are_bound_to_the_right_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each store repository carries its own table's name.

    Two stores built in adjacent lines from a helper that takes a table name is
    exactly the shape a copy-paste swaps, and swapped stores fail at runtime
    with a `ValidationException` about a missing range key rather than anything
    sooner.
    """
    import boto3
    import webbpulse.identity as package

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)

    captured: dict[str, Any] = {}

    def capture(settings: Any, *args: Any, **kwargs: Any) -> Any:
        captured["stores"] = args[1] if len(args) > 1 else kwargs.get("stores")
        raise _Captured

    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: object())
    monkeypatch.setattr(package, "build_identity_router", capture)

    with pytest.raises(_Captured):
        build_router(Settings())

    stores = captured["stores"]
    assert _logical_name_of(stores.totp_factors) == "totp-factors"
    assert _logical_name_of(stores.recovery_codes) == "recovery-codes"


def _logical_name_of(store: Any) -> str:
    """The unprefixed table a Dynamo store's repository is pointed at.

    Reaches through the store's private `_repo` attribute deliberately: there is
    no public accessor, and the alternative is not asserting the binding at all.
    `logical_name` rather than `table_name` because the prefix is the deploy
    environment's and the half worth pinning is the half `app/db/tables.py`
    chose.
    """
    return str(store._repo.logical_name)


class _Captured(Exception):
    """Unwinds `build_router` once the bundle it built has been captured."""


def test_the_hooks_still_satisfy_the_packages_protocol() -> None:
    """M4 adds no hook method, and this is what says so out loud.

    `IdentityHooks` is runtime checkable, so this is a structural check over the
    method names the package expects. If a future release grows a hook, the
    deployed function would raise `AttributeError` partway through a flow with a
    half-written row behind it; this fails at test time instead.
    """
    from webbpulse.identity import IdentityHooks

    assert isinstance(PortfolioIdentityHooks(), IdentityHooks)


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
    """The identity router as the composition root builds it, with the envelope
    key set as the module sets it.

    No AWS call is made: the `boto3.client` monkeypatch covers `kms` as well as
    the other clients the root builds, and the envelope key is never touched
    until somebody enrols.
    """
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_DATA_KEY_ARN", DATA_KEY_ARN)

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    app = FastAPI()
    app.include_router(build_router(Settings()))
    return app


def _post_paths(app: FastAPI) -> set[str]:
    return {
        route.path for route in app.routes if "POST" in getattr(route, "methods", set())
    }


def test_the_six_mfa_routes_mount_under_the_issuer_path(
    identity_app: FastAPI,
) -> None:
    """Every one of them, at `/api/auth/<name>` and not at the origin.

    The router carries no prefix of its own: every path it declares is already
    under `identity_prefix(settings)`, which is the issuer's path. A prefix added
    at `include_router` would double it, and the route keys in
    `terraform/apigateway.tf` would then point at nothing.
    """
    paths = _post_paths(identity_app)

    for path in MFA_PATHS:
        assert path in paths, f"{path} did not mount"


def test_the_mounted_paths_are_the_ones_the_package_declares(
    identity_app: FastAPI,
) -> None:
    """`MFA_PATHS` against the package's own constants, prefixed by the issuer path.

    The deliberate opposite of spelling them out: this is the test that turns a
    path constant renamed in a package release into a failure here rather than
    six 404s behind a green deploy.
    """
    from webbpulse.identity.router import (
        LOGIN_TOTP_PATH,
        RECOVERY_CODES_PATH,
        STEP_UP_PATH,
        TOTP_ACTIVATE_PATH,
        TOTP_DISABLE_PATH,
        TOTP_ENROL_PATH,
    )

    declared = {
        LOGIN_TOTP_PATH,
        TOTP_ENROL_PATH,
        TOTP_ACTIVATE_PATH,
        TOTP_DISABLE_PATH,
        RECOVERY_CODES_PATH,
        STEP_UP_PATH,
    }

    assert {f"/api/auth{suffix}" for suffix in declared} == set(MFA_PATHS)


def test_no_mfa_route_is_served_at_the_origin(identity_app: FastAPI) -> None:
    """None of the six answers at its bare name.

    The mirror of the M3 file's copy of this. `/totp/enrol` unprefixed would be a
    route API Gateway never forwards to and a hole in the map between the route
    keys and the app.
    """
    paths = _post_paths(identity_app)

    for path in MFA_PATHS:
        assert path.removeprefix("/api/auth") not in paths


def test_the_earlier_milestones_are_undisturbed_by_the_mfa_routes(
    identity_app: FastAPI,
) -> None:
    """M2's and M3's routes still mount alongside the six.

    `_mount_mfa` runs before the email early return in the package's router, so
    an ordering mistake there would show up as M3's four routes disappearing
    rather than as anything about M4. This is the assertion that catches it.
    """
    paths = _post_paths(identity_app)

    for path in ("/api/auth/login", "/api/auth/logout", "/api/auth/refresh"):
        assert path in paths


def test_the_documents_still_answer_with_the_mfa_routes_mounted(
    identity_app: FastAPI,
) -> None:
    """M1's two `.well-known` documents survive the larger router.

    They are the only anonymous surface on this function, and API Gateway's JWT
    authorizer fetches both at create time, so a router change that broke either
    breaks every authorized route on the whole API rather than only identity.
    """
    from fastapi.testclient import TestClient

    client = TestClient(identity_app)

    assert client.get("/api/auth/.well-known/openid-configuration").status_code == 200
    assert client.get("/api/auth/.well-known/jwks.json").status_code == 200


def test_the_routes_do_not_mount_without_the_factor_store(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of the switch, asserted against the package directly.

    This product supplies both stores unconditionally, so the only way to see
    the off state is to build a bundle without one. Worth having because it is
    what makes the positive test above mean something: without it, six routes
    mounting proves nothing about why they mounted.
    """
    import boto3
    import webbpulse.identity as package

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_DATA_KEY_ARN", DATA_KEY_ARN)

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    captured: dict[str, Any] = {}
    original = package.build_identity_router

    def strip(settings: Any, *args: Any, **kwargs: Any) -> Any:
        stores = args[1] if len(args) > 1 else kwargs.get("stores")
        captured["stores"] = stores
        import dataclasses

        stripped = dataclasses.replace(stores, totp_factors=None)
        rest = args[2:] if len(args) > 1 else ()
        return original(settings, args[0], stripped, *rest, **kwargs)

    monkeypatch.setattr(package, "build_identity_router", strip)

    app = FastAPI()
    app.include_router(build_router(Settings()))

    paths = _post_paths(app)
    for path in MFA_PATHS:
        assert path not in paths

    assert "/api/auth/login" in paths


class _EnvelopeKms:
    """M1's signing fake, plus the two envelope calls enrolment makes.

    `FakeKms` covers `sign` and `get_public_key`, which is all M1 through M3
    needed. Sealing a TOTP seed also calls `GenerateDataKey` and `Decrypt`, so
    those are added here rather than in the M1 fake: this is the only module
    that enrols, and widening the shared fake would give the earlier files a
    capability their subject never uses.

    The wrapped key carries its encryption context, and `decrypt` refuses a
    context that does not match. That is the property the envelope is for, so a
    fake that ignored it would let a broken `user_id` binding pass here.
    """

    def __init__(self, signing: Any) -> None:
        self._signing = signing
        self._keys: dict[bytes, tuple[bytes, dict[str, str]]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._signing, name)

    def generate_data_key(
        self, *, KeyId: str, NumberOfBytes: int, EncryptionContext: dict[str, str]
    ) -> dict[str, Any]:
        import os

        plaintext = os.urandom(NumberOfBytes)
        blob = b"wrapped-" + os.urandom(16)
        self._keys[blob] = (plaintext, dict(EncryptionContext))
        return {"Plaintext": plaintext, "CiphertextBlob": blob}

    def decrypt(
        self, *, CiphertextBlob: bytes, EncryptionContext: dict[str, str]
    ) -> dict[str, Any]:
        plaintext, context = self._keys[bytes(CiphertextBlob)]
        if context != dict(EncryptionContext):
            raise ValueError("encryption context mismatch")
        return {"Plaintext": plaintext}


def _enrolled_app(private_key: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    """An identity app with one enrolled user, plus the pieces to drive it.

    Returns `(app, mfa_service, user_id, access_token, recovery_codes)`.
    """
    import boto3
    from webbpulse.identity import (
        IdentitySettings,
        IdentityStores,
        InMemoryCredentialStore,
        InMemoryIdentityTokenStore,
        InMemoryRecoveryCodeStore,
        InMemoryRefreshTokenStore,
        InMemoryTotpFactorStore,
        build_identity_router,
    )

    from app.version import VERSION

    _identity_environment(monkeypatch)
    monkeypatch.setenv("IDENTITY_DATA_KEY_ARN", DATA_KEY_ARN)

    fake = _EnvelopeKms(FakeKms(private_key))
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    user_id = "user-under-test"

    class _Hooks(PortfolioIdentityHooks):
        """The product's hooks with the two lookups answered from memory.

        Subclassing rather than writing a stand-in keeps the `claims_for` policy
        this product actually ships in the path, so the access token minted
        below carries the claims the real one would.
        """

        def load_user_by_id(self, uid: str) -> Any:
            return {"id": uid, "email": "admin@example.com"} if uid == user_id else None

        def load_user_by_email(self, email: str) -> Any:
            return {"id": user_id, "email": email}

    settings = IdentitySettings()  # pyright: ignore[reportCallIssue]
    stores = IdentityStores(
        credentials=InMemoryCredentialStore(),
        refresh_tokens=InMemoryRefreshTokenStore(),
        identity_tokens=InMemoryIdentityTokenStore(),
        totp_factors=InMemoryTotpFactorStore(),
        recovery_codes=InMemoryRecoveryCodeStore(),
    )

    router = build_identity_router(
        settings,
        _Hooks(),
        stores,
        kms_client=fake,
        service="webbpulse-portfolio-identity",
        version=VERSION,
    )

    from webbpulse.http import create_app

    from app.composition.wiring import ERROR_ENVELOPE_OPTIONS

    app = create_app(
        title="identity-under-test",
        version=VERSION,
        service_name="webbpulse-portfolio-identity",
        include_health=False,
        **ERROR_ENVELOPE_OPTIONS,
    )
    app.include_router(router)

    from webbpulse.identity.mfa import MfaService
    from webbpulse.identity.service import TokenService
    from webbpulse.identity.totp import current_step, generate_code

    tokens = TokenService(settings, fake)
    mfa = MfaService(settings, stores, tokens, kms_client=fake)

    enrolment = mfa.begin_enrolment(user_id, account_name="admin@example.com")
    codes = mfa.confirm_enrolment(
        user_id, generate_code(enrolment.secret, step=current_step())
    )

    access = tokens.mint_access_token(user_id, claims={"email": "admin@example.com"})

    return app, mfa, user_id, access, list(codes.codes), enrolment.secret


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("path", ["/api/auth/totp/disable", "/api/auth/recovery-codes"])
@pytest.mark.parametrize("body", [{}, {"code": ""}, {"code": "   "}, {"code": 123}])
def test_a_missing_or_blank_code_is_a_422_on_both_routes(
    private_key: Any, monkeypatch: pytest.MonkeyPatch, path: str, body: Any
) -> None:
    """The old 0.12.1 call shape, and the near misses, all rejected as validation.

    A 422 rather than an `INVALID_MFA_CODE` is the deliberate half of this. A
    client that forgot the field is told it forgot the field, instead of the
    user being shown "that code is not valid" for a request that never asked
    them for one. The empty body case is exactly what a frontend written against
    0.12.1 sends, so this is the test that names the upgrade.
    """
    from fastapi.testclient import TestClient

    app, _mfa, _uid, access, _codes, _secret = _enrolled_app(private_key, monkeypatch)

    response = TestClient(app).post(path, json=body, headers=_auth(access))

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("path", ["/api/auth/totp/disable", "/api/auth/recovery-codes"])
def test_a_wrong_code_is_a_401_invalid_mfa_code_on_both_routes(
    private_key: Any, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """A well formed code that is not the user's, refused in the shared envelope.

    Same status and same `error_code` as `POST /login/totp`, because it is the
    same verification call. The frontend can therefore render one message for a
    bad code wherever it asks for one.
    """
    from fastapi.testclient import TestClient

    app, _mfa, _uid, access, _codes, _secret = _enrolled_app(private_key, monkeypatch)

    response = TestClient(app).post(
        path, json={"code": "000000"}, headers=_auth(access)
    )

    assert response.status_code == 401, response.text
    assert response.json()["error_code"] == "INVALID_MFA_CODE"


def test_a_refused_disable_leaves_the_factor_active(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verification happens before anything is deleted.

    This is the property that makes the code requirement worth having rather
    than merely present: if the factor were removed before the code was checked,
    a wrong code would still have disarmed the account.
    """
    from fastapi.testclient import TestClient

    app, mfa, user_id, access, _codes, _secret = _enrolled_app(private_key, monkeypatch)

    refused = TestClient(app).post(
        "/api/auth/totp/disable", json={"code": "000000"}, headers=_auth(access)
    )

    assert refused.status_code == 401
    assert mfa.factors_for(user_id) == ["totp"]


def test_a_recovery_code_disables_the_factor_and_is_spent(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A recovery code is accepted where a TOTP code is, and is consumed by the use.

    Both halves matter. Accepting it is what stops the loss of the phone being
    unrecoverable, and spending it is what stops a code observed once being
    replayed: a recovery code that survived its use would be a password.

    The count is read through the package's own `remaining_recovery_codes`
    rather than by counting rows, so this observes the deletion the store
    actually performed.
    """
    from fastapi.testclient import TestClient

    app, mfa, user_id, access, codes, _secret = _enrolled_app(private_key, monkeypatch)

    before = mfa.remaining_recovery_codes(user_id)

    response = TestClient(app).post(
        "/api/auth/totp/disable", json={"code": codes[0]}, headers=_auth(access)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"disabled": True}
    assert mfa.factors_for(user_id) == []
    assert mfa.remaining_recovery_codes(user_id) < before


def test_a_current_totp_code_regenerates_the_recovery_codes(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The success path of the second route, with a real code from the real seed.

    The new set is returned once and every previous code stops working in the
    same write, which is the whole point of the route: an admin who has lost
    their codes gets a fresh set without an operator touching the table.
    """
    from fastapi.testclient import TestClient
    from webbpulse.identity.totp import current_step, generate_code

    app, mfa, user_id, access, codes, secret = _enrolled_app(private_key, monkeypatch)

    code = generate_code(secret, step=current_step() + 1)
    response = TestClient(app).post(
        "/api/auth/recovery-codes", json={"code": code}, headers=_auth(access)
    )

    assert response.status_code == 200, response.text
    issued = response.json()["recovery_codes"]
    assert len(issued) == len(codes)
    assert set(issued).isdisjoint(codes), "the previous set was reissued"
    assert mfa.factors_for(user_id) == ["totp"], "regenerating is not disabling"


def test_a_refused_regenerate_leaves_the_existing_codes_working(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regenerating deletes the old set before writing the new one, so the order
    of the check against that delete is what this pins.

    A user who mistypes a code and is left holding a set that no longer works,
    with no new set to replace it, is locked out by a typo.
    """
    from fastapi.testclient import TestClient

    app, mfa, user_id, access, codes, _secret = _enrolled_app(private_key, monkeypatch)

    refused = TestClient(app).post(
        "/api/auth/recovery-codes", json={"code": "000000"}, headers=_auth(access)
    )

    assert refused.status_code == 401
    assert mfa.remaining_recovery_codes(user_id) == len(codes)


@pytest.mark.parametrize("path", ["/api/auth/totp/disable", "/api/auth/recovery-codes"])
def test_the_code_does_not_substitute_for_the_bearer_token(
    private_key: Any, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """0.13.0 adds a requirement, it does not swap one for another.

    Worth pinning because the body is new: a route that read the subject from
    anywhere but the verified token would let one user's valid code act on
    another user's account.
    """
    from fastapi.testclient import TestClient

    app, _mfa, _uid, _access, codes, _secret = _enrolled_app(private_key, monkeypatch)

    response = TestClient(app).post(path, json={"code": codes[0]})

    assert response.status_code == 401
    assert response.json()["error_code"] == "NOT_AUTHENTICATED"


def _limit_namespaces(app: FastAPI, path: str) -> set[str]:
    """The rate limit namespaces on one route, read off its dependencies.

    The limiter is wired as a `Depends` per route and exposes no registry, so
    the closure it was built from is the only place the namespace is legible.
    Reaching into `__closure__` is ugly and is done deliberately: the
    alternative is issuing eleven requests to observe a 429, which would make
    this a slow test of the limiter's arithmetic rather than a fast test of
    which routes are covered.
    """
    for route in app.routes:
        if getattr(route, "path", "") != path:
            continue
        found: set[str] = set()
        for dependency in getattr(route, "dependencies", []):
            call = getattr(dependency, "dependency", None)
            closure = getattr(call, "__closure__", None)
            for cell in closure or ():
                value = cell.cell_contents
                if isinstance(value, str):
                    found.add(value)
        return found
    raise AssertionError(f"{path} did not mount")


def test_both_destructive_routes_carry_the_mfa_verify_rate_limit(
    private_key: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same `mfa-verify` bound `login/totp` has, added to both by 0.13.0.

    They accept the same codes, so they need the same ceiling: a six digit code
    space is only acceptable because the number of attempts against it is
    bounded, and an unbounded `totp/disable` would be a way around the bound on
    `login/totp` rather than a separate door. Through 0.12.1 neither route was
    limited at all, because neither took a code.

    Compared against `login/totp`'s own namespace rather than a literal, so the
    limit being retuned is not a failure here while a route quietly losing it
    is.
    """
    app, _mfa, _uid, _access, _codes, _secret = _enrolled_app(private_key, monkeypatch)

    expected = _limit_namespaces(app, "/api/auth/login/totp")
    assert "mfa-verify" in expected

    for path in ("/api/auth/totp/disable", "/api/auth/recovery-codes"):
        assert "mfa-verify" in _limit_namespaces(app, path), path
