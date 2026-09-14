"""M1: the identity function's discovery document and JWKS, as this product wires
them.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from webbpulse.testing import FakeKms

cryptography = pytest.importorskip("cryptography")

KEY_ARN = "arn:aws:kms:us-west-2:621554169154:key/11111111-2222-3333-4444-555555555555"

ISSUER = "https://api.staging.webbpulse.com/api/auth"

AUDIENCE = "webbpulse-portfolio-staging-api"


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
def client(identity_env: None, rsa_key: Any, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The identity router mounted the way the composition root mounts it."""
    import boto3

    from app.composition.identity import build_router
    from app.composition.settings import Settings

    fake = FakeKms(rsa_key)
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
