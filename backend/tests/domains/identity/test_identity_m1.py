"""M1: the identity function's discovery document and JWKS, as this product wires
them.
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

ISSUER = "https://api.staging.webbpulse.com/api/auth"

AUDIENCE = "webbpulse-portfolio-staging-api"


class FakeKms:
    """A KMS client for one key, signing for real with a local private key."""

    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        """Hold the RSA key this fake KMS signs with."""
        self._key = key

    def _der(self) -> bytes:
        """The public key in DER SubjectPublicKeyInfo form."""
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_public_key(self, *, KeyId: str) -> dict[str, Any]:
        """Answer the KMS GetPublicKey shape for the held key."""
        from webbpulse.identity import KMS_SIGNING_ALGORITHM

        return {
            "KeyId": KeyId,
            "PublicKey": self._der(),
            "KeySpec": "RSA_2048",
            "KeyUsage": "SIGN_VERIFY",
            "SigningAlgorithms": [KMS_SIGNING_ALGORITHM],
        }

    def sign(self, *, KeyId: str, Message: bytes, MessageType: str, SigningAlgorithm: str) -> dict[str, Any]:
        """Sign a prehashed message the way KMS would."""
        signature = self._key.sign(Message, padding.PKCS1v15(), utils.Prehashed(hashes.SHA256()))
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
    """The `IDENTITY_*` environment `terraform/lambda_domains.tf` sets."""
    monkeypatch.setenv("IDENTITY_ENVIRONMENT", "staging")
    monkeypatch.setenv("IDENTITY_ISSUER", ISSUER)
    monkeypatch.setenv("IDENTITY_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("IDENTITY_SIGNING_KEY_ARNS", json.dumps([KEY_ARN]))
    monkeypatch.setenv("IDENTITY_COOKIE_DOMAIN", "staging.webbpulse.com")
    monkeypatch.setenv("IDENTITY_RP_ID", "staging.webbpulse.com")


@pytest.fixture
def client(identity_env: None, private_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The identity router mounted the way the composition root mounts it."""
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    fake = FakeKms(private_key)
    monkeypatch.setattr(boto3, "client", lambda service, *a, **kw: fake)

    settings = Settings()
    app = FastAPI()
    app.include_router(build_router(settings))
    return TestClient(app)


def test_discovery_is_served_under_the_issuer_path_with_the_configured_issuer(
    client: TestClient,
) -> None:
    """The issuer round trips byte for byte, at the path the authorizer fetches."""
    response = client.get("/api/auth/.well-known/openid-configuration")

    assert response.status_code == 200
    assert response.json()["issuer"] == ISSUER


def test_discovery_points_at_a_jwks_uri_that_is_actually_served(
    client: TestClient,
) -> None:
    """The link the authorizer follows, resolved rather than assumed."""
    discovery = client.get("/api/auth/.well-known/openid-configuration").json()
    jwks_uri = discovery["jwks_uri"]

    assert jwks_uri.startswith("https://api.staging.webbpulse.com/")
    path = jwks_uri.removeprefix("https://api.staging.webbpulse.com")
    assert client.get(path).status_code == 200


def test_the_jwks_publishes_one_rs256_key_for_the_configured_arn(
    client: TestClient,
) -> None:
    """One key in, one key out, and the algorithm the authorizer requires."""
    keys = client.get("/api/auth/.well-known/jwks.json").json()["keys"]

    assert len(keys) == 1
    assert keys[0]["kty"] == "RSA"
    assert keys[0]["alg"] == "RS256"
    assert keys[0]["use"] == "sig"
    assert keys[0]["kid"]


def test_the_documents_carry_the_cache_control_headers(client: TestClient) -> None:
    """The headers survive the mount, which is the only thing they depend on."""
    from webbpulse.identity.router import DISCOVERY_CACHE_CONTROL, JWKS_CACHE_CONTROL

    discovery = client.get("/api/auth/.well-known/openid-configuration")
    jwks = client.get("/api/auth/.well-known/jwks.json")

    assert discovery.headers["cache-control"] == DISCOVERY_CACHE_CONTROL
    assert jwks.headers["cache-control"] == JWKS_CACHE_CONTROL


def test_the_health_route_answers(client: TestClient) -> None:
    """The identity function's own health route, below the issuer path."""
    response = client.get("/api/auth/health")

    assert response.status_code == 200
