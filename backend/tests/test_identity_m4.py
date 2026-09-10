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

# M1's KMS fake, issuer and audience, reused for the reason the M2 and M3 files
# give: they are the values `terraform/lambda_domains.tf` sets, and a second
# copy here would be a second place for a rename to be missed.
from .test_identity_m1 import AUDIENCE, ISSUER, KEY_ARN, FakeKms

# The six M4 paths, spelled out rather than imported from the package, for the
# same reason `EMAIL_PATHS` is in the M3 file: a list derived from the thing it
# checks cannot notice that the thing moved. One test below does compare this
# tuple against the package's own constants, which is the deliberate opposite
# and is what turns a rename into a failure here rather than a 404 in staging.
# `terraform/apigateway.tf` carries the same six as route keys and
# `tests/entrypoints/test_gateway_routes.py` pins those.
MFA_PATHS = (
    "/api/auth/login/totp",
    "/api/auth/totp/enrol",
    "/api/auth/totp/activate",
    "/api/auth/totp/disable",
    "/api/auth/recovery-codes",
    "/api/auth/step-up",
)

#: The envelope key ARN the fixture sets. Not the real one: the module derives
#: that from the KMS key it creates and passes it in as `IDENTITY_DATA_KEY_ARN`.
#: What matters here is only that the settings pick the value up under that name.
DATA_KEY_ARN = (
    "arn:aws:kms:us-west-2:621554169154:key/99999999-8888-7777-6666-555555555555"
)


# ---------------------------------------------------------------------------
# The two tables
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# The envelope key setting
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# The composition root
# ---------------------------------------------------------------------------


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
        # `build_router` passes hooks and stores positionally, so the bundle is
        # the second of them, exactly as the M3 file's copy of this explains.
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


# ---------------------------------------------------------------------------
# The hooks protocol
# ---------------------------------------------------------------------------


def test_the_hooks_still_satisfy_the_packages_protocol() -> None:
    """M4 adds no hook method, and this is what says so out loud.

    `IdentityHooks` is runtime checkable, so this is a structural check over the
    method names the package expects. If a future release grows a hook, the
    deployed function would raise `AttributeError` partway through a flow with a
    half-written row behind it; this fails at test time instead.
    """
    from webbpulse.identity import IdentityHooks

    assert isinstance(PortfolioIdentityHooks(), IdentityHooks)


# ---------------------------------------------------------------------------
# The mount
# ---------------------------------------------------------------------------


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

    # And the earlier milestones are still there, which is the point: a missing
    # store takes the six routes and nothing else.
    assert "/api/auth/login" in paths
