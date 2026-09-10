"""M1: the identity function's discovery document and JWKS, as this product wires them.

What is worth testing here is the seam, not the package. `webbpulse.identity`'s
own suite already proves the router serves a well formed discovery document, a
JWKS with one entry per configured key, and the two `Cache-Control` headers, and
re-asserting that here would only pin the package's behaviour twice. What no
test in the package can cover is whether *this* product hands it the right
settings and mounts the result where the documents have to appear, which is the
half that was wrong in the M0 spike and the half an outage comes from.

So these tests read `IDENTITY_*` out of the environment exactly as
`terraform/lambda_domains.tf` sets it, build the router through
`app/composition/identity.py`, and assert on the served documents:

- the issuer in the document is the issuer Terraform configured, byte for byte,
  because API Gateway compares that string to the `iss` claim and to its own
  configured issuer, and a mismatch denies every request with nothing in any log
- both documents answer under the issuer's own path, because API Gateway appends
  `/.well-known/openid-configuration` to the issuer path included, and follows
  the `jwks_uri` it reads back literally
- the JWKS key is RS256 and carries the `kid` the token service will stamp
- the `Cache-Control` headers survive the mount, since they are the only thing
  limiting how often API Gateway refetches

The KMS client is a fake that signs with local RSA keys, following
`MultiKeyFakeKms` in the package's `tests/test_identity_m1.py`. moto is not
usable for this: its asymmetric `get_public_key` returns a null `KeySpec` and
its signatures do not verify, so a test built on it would pass while the real
thing failed.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import (  # noqa: E402
    padding,
    rsa,
    utils,
)

KEY_ARN = "arn:aws:kms:us-west-2:621554169154:key/11111111-2222-3333-4444-555555555555"

#: The issuer exactly as `local.identity_issuer` renders it for staging. The
#: `/api/auth` path is the standard's shape and the host is `local.api_host`.
ISSUER = "https://api.staging.webbpulse.com/api/auth"

#: `local.identity_audience`, which is `webbpulse-portfolio-<env>-api`.
AUDIENCE = "webbpulse-portfolio-staging-api"


class FakeKms:
    """A KMS client for one key, signing for real with a local private key.

    Faithful in the two ways the rendered documents depend on: it signs the
    digest it is handed without re-hashing it, which is what `MessageType`
    `DIGEST` means, and it returns the DER SubjectPublicKeyInfo that the `kid`
    is the base64url SHA-256 of. It differs from KMS only in who holds the key.
    """

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._key = key

    def _der(self) -> bytes:
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_public_key(self, *, KeyId: str) -> dict[str, Any]:
        from webbpulse.identity import KMS_SIGNING_ALGORITHM

        return {
            "KeyId": KeyId,
            "PublicKey": self._der(),
            "KeySpec": "RSA_2048",
            "KeyUsage": "SIGN_VERIFY",
            "SigningAlgorithms": [KMS_SIGNING_ALGORITHM],
        }

    def sign(
        self, *, KeyId: str, Message: bytes, MessageType: str, SigningAlgorithm: str
    ) -> dict[str, Any]:
        signature = self._key.sign(
            Message, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256())
        )
        return {
            "KeyId": KeyId,
            "Signature": signature,
            "SigningAlgorithm": SigningAlgorithm,
        }


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    """One 2048-bit key for the module. Generation is slow enough to share."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `IDENTITY_*` environment `terraform/lambda_domains.tf` sets.

    Written out as environment variables rather than passed as keyword
    arguments because that is the actual interface: `IdentitySettings` is a
    `BaseSettings` with `env_prefix="IDENTITY_"`, and the product passes it
    nothing. A test that constructed the settings directly would not notice a
    Terraform variable that was renamed or never set.

    `IDENTITY_SIGNING_KEY_ARNS` is JSON because `jsonencode` is what renders it.
    The settings deliberately refuse a bare comma separated list, so this format
    is load bearing rather than incidental.
    """
    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_RP_ID", "staging.webbpulse.com")


@pytest.fixture
def client(
    identity_env: None, private_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """The identity router mounted the way the composition root mounts it.

    At the issuer's path, through the same `identity_mount_prefix` the
    composition root uses, so a change to how the mount point is derived shows
    up here rather than only in production. The KMS client is injected
    by patching `boto3.client`, so the code under test is the real
    `build_router` including its own client construction rather than a
    reimplementation of it that could drift.
    """
    import boto3

    from app.composition.identity import build_router, identity_mount_prefix
    from app.composition.settings import Settings

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    settings = Settings()
    app = FastAPI()
    app.include_router(build_router(settings), prefix=identity_mount_prefix(settings))
    return TestClient(app)


def test_discovery_is_served_under_the_issuer_path_with_the_configured_issuer(
    client: TestClient,
) -> None:
    """The issuer round trips byte for byte, at the path the authorizer fetches.

    Both halves matter and they fail differently. A wrong path is a 404 the
    `CreateAuthorizer` call reports as a `BadRequestException` at apply time,
    which is loud. A wrong issuer string applies cleanly and then denies every
    request at runtime, which is not, and a trailing slash is the classic way to
    produce one. This asserts equality rather than a prefix match for that
    reason.
    """
    response = client.get("/api/auth/.well-known/openid-configuration")

    assert response.status_code == 200
    assert response.json()["issuer"] == ISSUER


def test_discovery_points_at_a_jwks_uri_that_is_actually_served(
    client: TestClient,
) -> None:
    """The link the authorizer follows, resolved rather than assumed.

    API Gateway does not guess the JWKS location: it reads `jwks_uri` out of the
    discovery document and fetches that. So the test follows the same link the
    same way instead of hardcoding the second path, which is what makes it a
    test of the pair rather than of two independent routes.
    """
    discovery = client.get("/api/auth/.well-known/openid-configuration").json()
    jwks_uri = discovery["jwks_uri"]

    assert jwks_uri.startswith("https://api.staging.webbpulse.com/")
    path = jwks_uri.removeprefix("https://api.staging.webbpulse.com")
    assert client.get(path).status_code == 200


def test_the_jwks_publishes_one_rs256_key_for_the_configured_arn(
    client: TestClient,
) -> None:
    """One key in, one key out, and the algorithm the authorizer requires.

    RS256 rather than the standard's preferred ES256 because the HTTP API JWT
    authorizer supports only RSA. `use` and `kid` are asserted because a JWKS
    entry missing either is one the authorizer will not select.
    """
    keys = client.get("/api/auth/.well-known/jwks.json").json()["keys"]

    assert len(keys) == 1
    assert keys[0]["kty"] == "RSA"
    assert keys[0]["alg"] == "RS256"
    assert keys[0]["use"] == "sig"
    assert keys[0]["kid"]


def test_the_documents_carry_the_cache_control_headers(client: TestClient) -> None:
    """The headers survive the mount, which is the only thing they depend on.

    They are what stops API Gateway refetching both documents on every
    validation, so losing them is a latency and cost regression that nothing
    else here would catch. The exact values are the package's, imported rather
    than written out so this tracks the package rather than duplicating it.
    """
    from webbpulse.identity.router import DISCOVERY_CACHE_CONTROL, JWKS_CACHE_CONTROL

    discovery = client.get("/api/auth/.well-known/openid-configuration")
    jwks = client.get("/api/auth/.well-known/jwks.json")

    assert discovery.headers["cache-control"] == DISCOVERY_CACHE_CONTROL
    assert jwks.headers["cache-control"] == JWKS_CACHE_CONTROL


def test_the_health_route_answers(client: TestClient) -> None:
    """The identity function's own health route, below the issuer path.

    It is `/api/auth/health` rather than `/health` because the whole router
    mounts at the issuer path, and that is the useful shape: `GET /health` at the
    origin already belongs to the `public` domain, so a second one there would
    collide. The route key in `terraform/apigateway.tf` matches this path.
    """
    response = client.get("/api/auth/health")

    assert response.status_code == 200
