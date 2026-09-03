from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import settings
from app.core import login_limiter as limiter_module
from app.core.admin import ensure_admin_seeded, reset_seed_state, seed_admin_user
from app.core.login_limiter import client_ip
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db import entities

LOGIN = "/api/v1/admin/login"
PROTECTED = "/api/v1/posts/admin"


def attempt(client, password="wrong", ip=None, username="adminuser"):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(
        LOGIN, json={"username": username, "password": password}, headers=headers
    )


class TestTokens:
    @pytest.mark.auth
    def test_expired_token_rejected(self, client: TestClient, test_admin_user):
        token = create_access_token(
            {"sub": test_admin_user["username"]}, expires_delta=timedelta(minutes=-1)
        )
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.auth
    def test_tampered_token_rejected(self, client: TestClient, test_admin_user):
        token = create_access_token({"sub": test_admin_user["username"]})
        head, payload, signature = token.split(".")
        tampered = ".".join(
            [head, payload, signature[:-2] + ("AA" if signature[-2:] != "AA" else "BB")]
        )
        response = client.get(
            PROTECTED, headers={"Authorization": f"Bearer {tampered}"}
        )
        assert response.status_code == 401

    @pytest.mark.auth
    def test_token_signed_with_other_key_rejected(
        self, client: TestClient, test_admin_user
    ):
        from jose import jwt

        token = jwt.encode(
            {"sub": test_admin_user["username"]}, "other-key", algorithm="HS256"
        )
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.auth
    def test_inactive_admin_token_rejected(self, client: TestClient, test_admin_user):
        entities.users.update(test_admin_user["id"], {"is_active": False})
        token = create_access_token({"sub": test_admin_user["username"]})
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert response.json()["detail"] == "User account is inactive"

    @pytest.mark.auth
    def test_wrong_scheme_rejected(self, client: TestClient):
        response = client.get(PROTECTED, headers={"Authorization": "Basic abc"})
        assert response.status_code == 403


class TestAdminSeeding:
    @pytest.mark.admin
    def test_first_request_seeds_admin_from_settings(self, client: TestClient):
        assert (
            entities.users.find_by_unique("username", settings.ADMIN_USERNAME) is None
        )
        client.get("/health")
        user = entities.users.find_by_unique("username", settings.ADMIN_USERNAME)
        assert user["is_admin"] is True and user["is_active"] is True
        assert user["email"] == settings.ADMIN_EMAIL
        response = attempt(
            client, settings.ADMIN_PASSWORD, username=settings.ADMIN_USERNAME
        )
        assert response.status_code == 200

    @pytest.mark.admin
    def test_seeding_is_idempotent(self):
        seed_admin_user()
        seed_admin_user()
        ensure_admin_seeded()
        assert entities.users.count() == 1

    @pytest.mark.admin
    def test_seeding_reconciles_existing_user(self, monkeypatch):
        entities.users.create(
            {
                "username": settings.ADMIN_USERNAME,
                "email": "stale@example.com",
                "hashed_password": get_password_hash("old"),
                "is_admin": False,
                "is_active": False,
            }
        )
        reset_seed_state()
        ensure_admin_seeded()
        user = entities.users.find_by_unique("username", settings.ADMIN_USERNAME)
        assert user["email"] == settings.ADMIN_EMAIL
        assert user["is_admin"] is True and user["is_active"] is True
        assert verify_password(settings.ADMIN_PASSWORD, user["hashed_password"])


class TestLoginLimiter:
    @pytest.mark.auth
    def test_lockout_after_max_failures(self, client: TestClient, test_admin_user):
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            assert attempt(client, ip="10.0.0.1").status_code == 401
        locked = attempt(client, ip="10.0.0.1")
        assert locked.status_code == 429
        body = locked.json()
        assert body["error"] == "Too Many Requests"
        assert body["retry_after"] >= 1
        assert "detail" in body
        assert locked.headers["Retry-After"] == str(body["retry_after"])
        assert attempt(client, "adminpassword123", ip="10.0.0.1").status_code == 429

    @pytest.mark.auth
    def test_lockout_is_per_ip(self, client: TestClient, test_admin_user):
        for _ in range(settings.LOGIN_MAX_FAILURES):
            attempt(client, ip="10.0.0.1")
        assert attempt(client, ip="10.0.0.2").status_code == 401
        assert attempt(client, "adminpassword123", ip="10.0.0.2").status_code == 200

    @pytest.mark.auth
    def test_success_clears_failures(self, client: TestClient, test_admin_user):
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            attempt(client, ip="10.0.0.1")
        assert attempt(client, "adminpassword123", ip="10.0.0.1").status_code == 200
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            assert attempt(client, ip="10.0.0.1").status_code == 401

    @pytest.mark.auth
    def test_lockout_expires(self, client: TestClient, test_admin_user, monkeypatch):
        for _ in range(settings.LOGIN_MAX_FAILURES):
            attempt(client, ip="10.0.0.1")
        assert attempt(client, "adminpassword123", ip="10.0.0.1").status_code == 429
        real_now = limiter_module.now()
        monkeypatch.setattr(
            limiter_module,
            "now",
            lambda: real_now + settings.LOGIN_FAILURE_WINDOW_SECONDS + 1,
        )
        assert attempt(client, "adminpassword123", ip="10.0.0.1").status_code == 200

    @pytest.mark.auth
    def test_unknown_usernames_count_as_failures(self, client: TestClient):
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            assert attempt(client, ip="10.0.0.3", username="nobody").status_code == 401
        assert attempt(client, ip="10.0.0.3", username="nobody").status_code == 429


class TestClientIp:
    @staticmethod
    def request(scope_extra=None, headers=(), client=("9.9.9.9", 1234)):
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
            "client": client,
        }
        scope.update(scope_extra or {})
        return Request(scope)

    @pytest.mark.unit
    def test_prefers_api_gateway_source_ip(self):
        request = self.request(
            {"aws.event": {"requestContext": {"http": {"sourceIp": "1.1.1.1"}}}},
            headers=[("x-forwarded-for", "2.2.2.2")],
        )
        assert client_ip(request) == "1.1.1.1"

    @pytest.mark.unit
    def test_rest_api_identity_source_ip(self):
        request = self.request(
            {"aws.event": {"requestContext": {"identity": {"sourceIp": "3.3.3.3"}}}}
        )
        assert client_ip(request) == "3.3.3.3"

    @pytest.mark.unit
    def test_forwarded_for_then_client_host(self):
        assert (
            client_ip(self.request(headers=[("x-forwarded-for", "2.2.2.2, 5.5.5.5")]))
            == "2.2.2.2"
        )
        assert client_ip(self.request()) == "9.9.9.9"
        assert client_ip(self.request(client=None)) == "unknown"

    @pytest.mark.unit
    def test_context_shape_is_tolerated(self):
        assert (
            client_ip(
                self.request(
                    {"aws.event": SimpleNamespace()} if False else {"aws.event": {}}
                )
            )
            == "9.9.9.9"
        )
