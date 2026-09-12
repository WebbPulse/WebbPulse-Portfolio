"""Token rejection, admin seeding and the per-IP login limiter."""

import json
import logging
from datetime import timedelta

import boto3
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import settings
from app.core import login_limiter as limiter_module
from app.core.login_limiter import REQUEST_CONTEXT_HEADER, client_ip
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db import client as db_client
from app.db import entities
from app.db.tables import META, RATE_LIMIT_TTL_ATTRIBUTE, RATE_LIMITS
from app.domains.identity.service import (
    ensure_admin_seeded,
    reset_seed_state,
    seed_admin_user,
)
from tests.envelope import error_message

LOGIN = "/api/v1/admin/login"
PROTECTED = "/api/v1/posts/admin"


def request_context_headers(ip, payload_format="2.0"):
    """The `x-amzn-request-context` header the Lambda Web Adapter forwards."""
    section = {"http": {"sourceIp": ip}} if payload_format == "2.0" else {"identity": {"sourceIp": ip}}
    return {REQUEST_CONTEXT_HEADER: json.dumps(section)}


def attempt(client, password="wrong", ip=None, username="adminuser"):
    """Post a login attempt, optionally from a given source IP."""
    headers = request_context_headers(ip) if ip else {}
    return client.post(LOGIN, json={"username": username, "password": password}, headers=headers)


class TestTokens:
    """Which bearer tokens the protected endpoints refuse."""

    @pytest.mark.auth
    def test_expired_token_rejected(self, client: TestClient, test_admin_user):
        """An expired token answers 401 and asks for Bearer."""
        token = create_access_token({"sub": test_admin_user["username"]}, expires_delta=timedelta(minutes=-1))
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.auth
    def test_tampered_token_rejected(self, client: TestClient, test_admin_user):
        """A token with an edited signature answers 401."""
        token = create_access_token({"sub": test_admin_user["username"]})
        head, payload, signature = token.split(".")
        tampered = ".".join([head, payload, signature[:-2] + ("AA" if signature[-2:] != "AA" else "BB")])
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {tampered}"})
        assert response.status_code == 401

    @pytest.mark.auth
    def test_token_signed_with_other_key_rejected(self, client: TestClient, test_admin_user):
        """A token signed with a foreign key answers 401."""
        import jwt

        token = jwt.encode({"sub": test_admin_user["username"]}, "other-key", algorithm="HS256")
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.auth
    def test_inactive_admin_token_rejected(self, client: TestClient, test_admin_user):
        """A valid token for a deactivated user answers 403."""
        entities.users.update(test_admin_user["id"], {"is_active": False})
        token = create_access_token({"sub": test_admin_user["username"]})
        response = client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert error_message(response) == "User account is inactive"

    @pytest.mark.auth
    def test_wrong_scheme_rejected(self, client: TestClient):
        """A non-Bearer scheme is unauthenticated, so 401 with a challenge."""
        response = client.get(PROTECTED, headers={"Authorization": "Basic abc"})
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"


class TestAdminSeeding:
    """Seeding the configured admin user."""

    @pytest.mark.admin
    def test_first_request_seeds_admin_from_settings(self, client: TestClient):
        """The first request seeds the admin from settings and that admin can log in."""
        assert entities.users.find_by_unique("username", settings.ADMIN_USERNAME) is None
        client.get("/health")
        user = entities.users.find_by_unique("username", settings.ADMIN_USERNAME)
        assert user["is_admin"] is True and user["is_active"] is True
        assert user["email"] == settings.ADMIN_EMAIL
        response = attempt(client, settings.ADMIN_PASSWORD, username=settings.ADMIN_USERNAME)
        assert response.status_code == 200

    @pytest.mark.admin
    def test_seeding_is_idempotent(self):
        """Repeated seeding leaves exactly one user."""
        seed_admin_user()
        seed_admin_user()
        ensure_admin_seeded()
        assert entities.users.count() == 1

    @pytest.mark.admin
    def test_seeding_reconciles_existing_user(self, monkeypatch):
        """Seeding repairs an existing row's email, flags and password."""
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
    """Locking out repeated failed logins."""

    @pytest.mark.auth
    def test_lockout_after_max_failures(self, client: TestClient, test_admin_user):
        """Hitting the limit answers 429 with Retry-After, even for a good password."""
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
        """A locked out IP does not affect another one."""
        for _ in range(settings.LOGIN_MAX_FAILURES):
            attempt(client, ip="10.0.0.1")
        assert attempt(client, ip="10.0.0.2").status_code == 401
        assert attempt(client, "adminpassword123", ip="10.0.0.2").status_code == 200

    @pytest.mark.auth
    def test_success_clears_failures(self, client: TestClient, test_admin_user):
        """A successful login resets the failure count."""
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            attempt(client, ip="10.0.0.1")
        assert attempt(client, "adminpassword123", ip="10.0.0.1").status_code == 200
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            assert attempt(client, ip="10.0.0.1").status_code == 401

    @pytest.mark.auth
    def test_lockout_expires(self, client: TestClient, test_admin_user, monkeypatch):
        """Once the window passes the lockout lifts."""
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
    def test_failures_accumulate_atomically(self, aws_tables):
        """Failures count up per key and stay separate between keys."""
        limiter = limiter_module.LoginLimiter(3, 60)
        assert limiter.record_failure("10.0.0.9") == 1
        assert limiter.record_failure("10.0.0.9") == 2
        assert limiter.record_failure("10.0.0.9") == 3
        assert limiter.retry_after("10.0.0.9") >= 1
        assert limiter.record_failure("10.0.0.8") == 1

    @pytest.mark.auth
    def test_expired_window_restarts_count(self, aws_tables, monkeypatch):
        """A failure after the window restarts the count at one."""
        limiter = limiter_module.LoginLimiter(3, 60)
        limiter.record_failure("10.0.0.9")
        limiter.record_failure("10.0.0.9")
        real_now = limiter_module.now()
        monkeypatch.setattr(limiter_module, "now", lambda: real_now + 61)
        assert limiter.record_failure("10.0.0.9") == 1
        assert limiter.retry_after("10.0.0.9") is None

    @pytest.mark.auth
    def test_unknown_usernames_count_as_failures(self, client: TestClient):
        """Attempts on a username that does not exist still count toward the lockout."""
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            assert attempt(client, ip="10.0.0.3", username="nobody").status_code == 401
        assert attempt(client, ip="10.0.0.3", username="nobody").status_code == 429


class TestClientIp:
    """The source IP the limiter keys on."""

    @staticmethod
    def request(scope_extra=None, headers=(), client=("9.9.9.9", 1234)):
        """Build a Request with the given scope extras, headers and peer address."""
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
            "client": client,
        }
        scope.update(scope_extra or {})
        return Request(scope)

    @pytest.mark.unit
    def test_adapter_header_payload_2_0(self):
        """HTTP APIs use payload format 2.0, where the IP is under `http`."""
        request = self.request(headers=[(REQUEST_CONTEXT_HEADER, json.dumps({"http": {"sourceIp": "1.1.1.1"}}))])
        assert client_ip(request) == "1.1.1.1"

    @pytest.mark.unit
    def test_adapter_header_payload_1_0(self):
        """REST APIs use payload format 1.0, where the IP is under `identity`."""
        request = self.request(
            headers=[
                (
                    REQUEST_CONTEXT_HEADER,
                    json.dumps({"identity": {"sourceIp": "3.3.3.3"}}),
                )
            ]
        )
        assert client_ip(request) == "3.3.3.3"

    @pytest.mark.unit
    def test_adapter_header_prefers_payload_2_0(self):
        """With both shapes present the payload 2.0 source IP wins."""
        request = self.request(
            headers=[
                (
                    REQUEST_CONTEXT_HEADER,
                    json.dumps(
                        {
                            "http": {"sourceIp": "1.1.1.1"},
                            "identity": {"sourceIp": "3.3.3.3"},
                        }
                    ),
                )
            ]
        )
        assert client_ip(request) == "1.1.1.1"

    @pytest.mark.unit
    def test_adapter_header_accepts_a_whole_event(self):
        """A context nested under `requestContext` is tolerated too."""
        request = self.request(
            headers=[
                (
                    REQUEST_CONTEXT_HEADER,
                    json.dumps({"requestContext": {"http": {"sourceIp": "4.4.4.4"}}}),
                )
            ]
        )
        assert client_ip(request) == "4.4.4.4"

    @pytest.mark.unit
    def test_mangum_scope_still_works(self):
        """Nothing runs under Mangum now, but `client_ip` still reads the scope."""
        request = self.request({"aws.event": {"requestContext": {"http": {"sourceIp": "1.1.1.1"}}}})
        assert client_ip(request) == "1.1.1.1"

    @pytest.mark.unit
    def test_mangum_scope_rest_shape(self):
        """The Mangum scope is read in the payload 1.0 shape too."""
        request = self.request({"aws.event": {"requestContext": {"identity": {"sourceIp": "3.3.3.3"}}}})
        assert client_ip(request) == "3.3.3.3"

    @pytest.mark.unit
    def test_adapter_header_wins_over_the_mangum_scope(self):
        """The adapter header takes precedence over the Mangum scope."""
        request = self.request(
            {"aws.event": {"requestContext": {"http": {"sourceIp": "3.3.3.3"}}}},
            headers=[(REQUEST_CONTEXT_HEADER, json.dumps({"http": {"sourceIp": "1.1.1.1"}}))],
        )
        assert client_ip(request) == "1.1.1.1"

    @pytest.mark.unit
    def test_forwarded_for_is_never_trusted(self):
        """The leftmost hop is caller controlled, so trusting it mints identities."""
        with_context = self.request(
            headers=[
                (REQUEST_CONTEXT_HEADER, json.dumps({"http": {"sourceIp": "1.1.1.1"}})),
                ("x-forwarded-for", "2.2.2.2"),
            ]
        )
        assert client_ip(with_context) == "1.1.1.1"

        without_context = self.request(headers=[("x-forwarded-for", "2.2.2.2, 5.5.5.5")])
        assert client_ip(without_context) == "9.9.9.9", "the peer, never the header"

    @pytest.mark.unit
    def test_falls_back_to_the_peer_address(self):
        """With no context the peer address is used, or unknown when there is none."""
        assert client_ip(self.request()) == "9.9.9.9"
        assert client_ip(self.request(client=None)) == "unknown"

    @pytest.mark.unit
    def test_malformed_header_degrades_instead_of_raising(self):
        """An unparseable context header falls back to the peer address."""
        request = self.request(headers=[(REQUEST_CONTEXT_HEADER, "{not json")])
        assert client_ip(request) == "9.9.9.9"

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "context",
        [
            {},
            {"http": {}},
            {"identity": {}},
            {"http": {"sourceIp": ""}},
            {"http": "nope"},
        ],
    )
    def test_a_context_without_a_usable_source_ip(self, context):
        """A context carrying no usable source IP falls back to the peer address."""
        request = self.request(headers=[(REQUEST_CONTEXT_HEADER, json.dumps(context))])
        assert client_ip(request) == "9.9.9.9"

    @pytest.mark.unit
    def test_an_empty_mangum_event_falls_through(self):
        """An empty Mangum event falls back to the peer address."""
        assert client_ip(self.request({"aws.event": {}})) == "9.9.9.9"


class TestLimiterTable:
    """The limiter items live in `<prefix>-rate-limits`, not in `meta`."""

    @pytest.mark.auth
    def test_items_are_written_to_the_rate_limits_table(self, aws_tables):
        """The failure counter lands in the rate-limits table."""
        limiter = limiter_module.LoginLimiter(3, 60)
        limiter.record_failure("10.0.0.7")

        table = db_client.table(RATE_LIMITS)
        item = table.get_item(Key=limiter.key("10.0.0.7")).get("Item")
        assert item is not None, "the counter must land in the rate-limits table"
        assert int(item["failures"]) == 1

    @pytest.mark.auth
    def test_the_ttl_attribute_matches_the_shared_package(self, aws_tables):
        """`webbpulse.ratelimit` names it `expires_at`, not the `ttl` meta uses."""
        limiter = limiter_module.LoginLimiter(3, 60)
        limiter.record_failure("10.0.0.7")

        item = db_client.table(RATE_LIMITS).get_item(Key=limiter.key("10.0.0.7"))["Item"]
        assert RATE_LIMIT_TTL_ATTRIBUTE in item
        assert "ttl" not in item

    @pytest.mark.auth
    def test_nothing_is_written_to_meta(self, aws_tables):
        """The limiter writes nothing to the meta table."""
        limiter = limiter_module.LoginLimiter(3, 60)
        limiter.record_failure("10.0.0.7")

        meta = db_client.table(META)
        assert meta.get_item(Key=limiter.key("10.0.0.7")).get("Item") is None


class TestLimiterFailsOpen:
    """The `rate-limits` table does not exist until PR 9 creates it."""

    @staticmethod
    def missing_table_limiter(monkeypatch):
        """A limiter pointed at a table that does not exist."""
        limiter = limiter_module.LoginLimiter(3, 60)
        resource = boto3.resource("dynamodb", region_name="us-west-2")
        absent = resource.Table("webbpulse-test-does-not-exist")
        monkeypatch.setattr(type(limiter), "table", property(lambda self: absent), raising=False)
        return limiter

    @pytest.mark.auth
    def test_record_failure_allows_the_request(self, aws_tables, monkeypatch):
        """An unparseable context header falls back to the peer address."""
        limiter = self.missing_table_limiter(monkeypatch)
        assert limiter.record_failure("10.0.0.6") == 0

    @pytest.mark.auth
    def test_retry_after_reports_no_lockout(self, aws_tables, monkeypatch):
        """With the table missing, no lockout is reported."""
        limiter = self.missing_table_limiter(monkeypatch)
        assert limiter.retry_after("10.0.0.6") is None

    @pytest.mark.auth
    def test_clear_does_not_raise(self, aws_tables, monkeypatch):
        """With the table missing, clearing a key is a no-op rather than an error."""
        limiter = self.missing_table_limiter(monkeypatch)
        limiter.clear("10.0.0.6")

    @pytest.mark.auth
    def test_the_failure_is_logged_as_failed_open(self, aws_tables, monkeypatch, caplog):
        """The WARNING is the compensating control; an alarm watches for it."""
        with caplog.at_level(logging.WARNING):
            self.missing_table_limiter(monkeypatch).record_failure("10.0.0.6")

        assert caplog.records, "a fail-open must not be silent"
        record = caplog.records[0]
        assert record.rate_limit_failed_open is True
        assert record.error_type == "ResourceNotFoundException"

    @pytest.mark.auth
    def test_login_still_answers_401_with_the_table_missing(self, client: TestClient, test_admin_user, monkeypatch):
        """With the table missing, clearing a key is a no-op rather than an error."""
        resource = boto3.resource("dynamodb", region_name="us-west-2")
        absent = resource.Table("webbpulse-test-does-not-exist")
        monkeypatch.setattr(
            limiter_module.LoginLimiter,
            "table",
            property(lambda self: absent),
        )
        for _ in range(settings.LOGIN_MAX_FAILURES + 2):
            assert attempt(client, ip="10.0.0.5").status_code == 401, "a broken limiter must never lock anyone out"
        assert attempt(client, "adminpassword123", ip="10.0.0.5").status_code == 200
