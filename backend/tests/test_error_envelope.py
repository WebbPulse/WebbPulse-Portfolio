"""The envelope's `error_code` and `details`, and what the `"detailed"` shape did
not change.
"""

import pytest
from starlette.testclient import TestClient

from app.composition.app import build_app
from app.composition.wiring import DOMAINS, ERROR_ENVELOPE, build_domain_app

UNAUTHORIZED_MESSAGE = "Invalid authentication credentials"
LOGIN_FAILED_MESSAGE = "Incorrect username or password"
NOT_FOUND_MESSAGE = "The requested resource was not found."
VALIDATION_MESSAGE = "Request validation failed."
INTERNAL_MESSAGE = "Internal server error."


def envelope(response):
    """The body, with the four fields that were always there checked."""
    body = response.json()
    assert body["success"] is False, body
    assert body["status"] == response.status_code, body
    assert body["request_id"], body
    return body


@pytest.mark.api
def test_a_rejected_token_carries_unauthorized(client: TestClient):
    """A rejected bearer token answers 401 with the UNAUTHORIZED code."""
    response = client.get(
        "/api/v1/posts/admin", headers={"Authorization": "Bearer invalid_token"}
    )

    assert response.status_code == 401
    body = envelope(response)
    assert body["error_code"] == "UNAUTHORIZED"
    assert body["message"] == UNAUTHORIZED_MESSAGE


@pytest.mark.api
def test_a_failed_login_carries_unauthorized(client: TestClient, test_admin_user):
    """The other 401, and the one a form actually shows a user."""
    response = client.post(
        "/api/v1/admin/login", json={"username": "adminuser", "password": "wrong"}
    )

    assert response.status_code == 401
    body = envelope(response)
    assert body["error_code"] == "UNAUTHORIZED"
    assert body["message"] == LOGIN_FAILED_MESSAGE


@pytest.mark.api
def test_an_unmatched_route_carries_not_found(client: TestClient):
    """An unrouted path answers 404 with the NOT_FOUND code."""
    response = client.get("/api/v1/no-such-route")

    assert response.status_code == 404
    body = envelope(response)
    assert body["error_code"] == "NOT_FOUND"
    assert body["message"] == NOT_FOUND_MESSAGE


@pytest.mark.api
def test_a_missing_item_carries_not_found(client: TestClient):
    """A 404 a route raised, not one Starlette produced."""
    response = client.get("/api/v1/projects/999999")

    assert response.status_code == 404
    body = envelope(response)
    assert body["error_code"] == "NOT_FOUND"
    assert body["message"] != NOT_FOUND_MESSAGE
    assert body["message"]


@pytest.mark.api
def test_a_rejected_body_carries_validation_error(client: TestClient):
    """A body that fails validation answers 422 with the VALIDATION_ERROR code."""
    response = client.post("/api/v1/admin/login", json={"username": 5})

    assert response.status_code == 422
    body = envelope(response)
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["message"] == VALIDATION_MESSAGE


@pytest.mark.api
def test_an_unhandled_exception_carries_internal_error():
    """The 500 handler, reached by an exception escaping a route."""
    app = build_app()

    @app.get("/api/v1/_raises_for_the_test")
    def _raises():
        """Route that raises, to reach the unhandled exception handler."""
        raise RuntimeError("deliberate, to reach the unhandled exception handler")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/_raises_for_the_test")

    assert response.status_code == 500
    body = envelope(response)
    assert body["error_code"] == "INTERNAL_ERROR"
    assert body["message"] == INTERNAL_MESSAGE
    assert "deliberate" not in response.text


@pytest.mark.api
@pytest.mark.parametrize(
    ("status", "expected_message", "expected_code"),
    [
        (401, UNAUTHORIZED_MESSAGE, "UNAUTHORIZED"),
        (404, NOT_FOUND_MESSAGE, "NOT_FOUND"),
        (422, VALIDATION_MESSAGE, "VALIDATION_ERROR"),
    ],
)
def test_messages_are_unchanged(
    client: TestClient, status, expected_message, expected_code
):
    """Every message is the string it was before the codes were turned on."""
    responses = {
        401: lambda: client.get(
            "/api/v1/posts/admin", headers={"Authorization": "Bearer invalid_token"}
        ),
        404: lambda: client.get("/api/v1/no-such-route"),
        422: lambda: client.post("/api/v1/admin/login", json={"username": 5}),
    }
    response = responses[status]()

    assert response.status_code == status
    body = envelope(response)
    assert body["message"] == expected_message
    assert body["error_code"] == expected_code


@pytest.mark.api
def test_the_base_fields_keep_their_order(client: TestClient):
    """`success`, `status`, `message`, `request_id`, then the additions."""
    response = client.get("/api/v1/no-such-route")

    assert list(response.json())[:4] == ["success", "status", "message", "request_id"]


@pytest.mark.api
def test_a_422_carries_one_details_entry_per_offending_field(client: TestClient):
    """The shape `@webbpulse/api-client` surfaces as `getWebbPulseError().details`."""
    response = client.post("/api/v1/admin/login", json={"username": 5})

    assert response.status_code == 422
    body = envelope(response)
    details = body["details"]
    assert isinstance(details, list)
    assert {entry["field"] for entry in details} == {"username", "password"}
    for entry in details:
        assert set(entry) == {"field", "message", "type"}
        assert entry["message"]
        assert entry["type"]


@pytest.mark.api
def test_the_legacy_errors_key_is_gone(client: TestClient):
    """`details` replaces `errors`; the `"detailed"` shape drops the legacy key."""
    response = client.post("/api/v1/admin/login", json={"username": 5})

    body = envelope(response)
    assert "errors" not in body


@pytest.mark.api
def test_a_non_validation_error_carries_no_details(client: TestClient):
    """`details` is omitted, not null, when there is nothing to put in it."""
    body = envelope(client.get("/api/v1/no-such-route"))

    assert "details" not in body


@pytest.mark.unit
def test_the_envelope_shape_is_detailed():
    """The switch itself, so changing it is a visible edit to this file."""
    assert ERROR_ENVELOPE == "detailed"


@pytest.mark.unit
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_every_deployed_domain_renders_the_code(domain):
    """Root B, per domain, not just root A."""
    with TestClient(build_domain_app(DOMAINS[domain])) as test_client:
        response = test_client.get("/no-such-route-in-any-domain")

    assert response.status_code == 404
    assert envelope(response)["error_code"] == "NOT_FOUND"
