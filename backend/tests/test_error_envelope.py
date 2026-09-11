"""The envelope's `error_code` and `details`, and what turning them on did not change.

Portfolio builds every application through `webbpulse.http.create_app`, whose
error handlers already rendered one body for every failure:
`{"success", "status", "message", "request_id"}`. Both options were off, so
`error_code` and `details` were absent keys rather than null ones, and
`frontend/src/services/api.ts` logged an `errorCode` that was always
`undefined`.

`ERROR_ENVELOPE_OPTIONS` in `app.composition.wiring` turns both on for both
composition roots at once. This module holds that to two claims.

**The codes are there, on every status a caller actually sees.** 401 for a
rejected credential, 404 for a route and for an item, 422 for a rejected body,
500 for an unhandled exception. A frontend that branches on `NOT_FOUND` rather
than on the text of a message needs the code on the failure it is branching on,
so the statuses are named individually rather than asserted in the abstract.

**Nothing else moved.** The option is additive by construction in the shared
package, but "additive" is exactly the kind of claim that is worth an assertion
rather than a comment: the messages here are the strings the existing suite and
the frontend already read, so a change to any of them would be a change to the
API whether or not a test named it. `test_messages_are_unchanged` pins them.

The 500 case registers a route that raises. There is no endpoint in the
application that fails on demand, and mocking one deep in a repository would
test the mock's placement rather than the handler, so the exception is raised
where an unhandled one would escape from: inside a route, below every
middleware `create_app` installed.
"""

import pytest
from starlette.testclient import TestClient

from app.composition.app import build_app
from app.composition.wiring import DOMAINS, ERROR_ENVELOPE_OPTIONS, build_domain_app

UNAUTHORIZED_MESSAGE = "Invalid authentication credentials"
LOGIN_FAILED_MESSAGE = "Incorrect username or password"
NOT_FOUND_MESSAGE = "The requested resource was not found."
VALIDATION_MESSAGE = "Request validation failed."
INTERNAL_MESSAGE = "Internal server error."


def envelope(response):
    """The body, with the four fields that were always there checked.

    `tests/envelope.py` does this for the message alone. This returns the whole
    body, because the assertions below are about the keys beside the message.
    """
    body = response.json()
    assert body["success"] is False, body
    assert body["status"] == response.status_code, body
    assert body["request_id"], body
    return body


@pytest.mark.api
def test_a_rejected_token_carries_unauthorized(client: TestClient):
    response = client.get(
        "/api/v1/posts/admin", headers={"Authorization": "Bearer invalid_token"}
    )

    assert response.status_code == 401
    body = envelope(response)
    assert body["error_code"] == "UNAUTHORIZED"
    assert body["message"] == UNAUTHORIZED_MESSAGE


@pytest.mark.api
def test_a_failed_login_carries_unauthorized(client: TestClient, test_admin_user):
    """The other 401, and the one a form actually shows a user.

    A wrong password and a rejected token are the same status and the same code,
    which is the point: the code says what happened to the request, and the
    message is what distinguishes them for a person reading it.
    """
    response = client.post(
        "/api/v1/admin/login", json={"username": "adminuser", "password": "wrong"}
    )

    assert response.status_code == 401
    body = envelope(response)
    assert body["error_code"] == "UNAUTHORIZED"
    assert body["message"] == LOGIN_FAILED_MESSAGE


@pytest.mark.api
def test_an_unmatched_route_carries_not_found(client: TestClient):
    response = client.get("/api/v1/no-such-route")

    assert response.status_code == 404
    body = envelope(response)
    assert body["error_code"] == "NOT_FOUND"
    assert body["message"] == NOT_FOUND_MESSAGE


@pytest.mark.api
def test_a_missing_item_carries_not_found(client: TestClient):
    """A 404 a route raised, not one Starlette produced.

    Both arrive through the same handler but by different paths: this one is an
    `HTTPException` a route raised with its own message, and the message has to
    survive the code being added beside it.
    """
    response = client.get("/api/v1/projects/999999")

    assert response.status_code == 404
    body = envelope(response)
    assert body["error_code"] == "NOT_FOUND"
    assert body["message"] != NOT_FOUND_MESSAGE
    assert body["message"]


@pytest.mark.api
def test_a_rejected_body_carries_validation_error(client: TestClient):
    response = client.post("/api/v1/admin/login", json={"username": 5})

    assert response.status_code == 422
    body = envelope(response)
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["message"] == VALIDATION_MESSAGE


@pytest.mark.api
def test_an_unhandled_exception_carries_internal_error():
    """The 500 handler, reached by an exception escaping a route.

    `raise_server_exceptions=False` makes the test client return the response
    the handler produced rather than re-raising, which is what a real client
    receives. Without it the exception propagates into the test and the envelope
    is never seen.
    """
    app = build_app()

    @app.get("/api/v1/_raises_for_the_test")
    def _raises():
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
    """Every message is the string it was before the codes were turned on.

    The whole argument for enabling `error_codes` is that it is additive. This
    is that argument as an assertion: the four base fields keep their values, so
    a caller rendering `message` sees exactly what it saw yesterday, and the
    code is a new key beside it rather than a replacement for it.
    """
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
    """`success`, `status`, `message`, `request_id`, then the additions.

    The shared package documents the order as part of the envelope, and the
    additions go after them. Asserting it here is cheap and catches a handler
    that rebuilt the body rather than adding to it.
    """
    response = client.get("/api/v1/no-such-route")

    assert list(response.json())[:4] == ["success", "status", "message", "request_id"]


@pytest.mark.api
def test_a_422_carries_one_details_entry_per_offending_field(client: TestClient):
    """The shape `@webbpulse/api-client` surfaces as `getWebbPulseError().details`.

    A list of `{"field", "message", "type"}`, with the leading `body` segment
    dropped so `field` is the name the form control already uses. That is what
    lets a form put a message beside the input that caused it instead of one
    banner for the whole request.
    """
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
def test_the_older_errors_key_is_untouched(client: TestClient):
    """`details` is added beside `errors`, not instead of it.

    `errors` carries the raw `loc` list FastAPI produces and predates the
    option. Dropping it would break anything already reading it, so the shared
    package keeps it unconditionally and this pins that.
    """
    response = client.post("/api/v1/admin/login", json={"username": 5})

    body = envelope(response)
    assert [entry["loc"] for entry in body["errors"]] == [
        ["body", "username"],
        ["body", "password"],
    ]


@pytest.mark.api
def test_a_non_validation_error_carries_no_details(client: TestClient):
    """`details` is omitted, not null, when there is nothing to put in it.

    The client types it as optional rather than nullable for exactly this
    reason: an absent key and an explicit null are different answers, and the
    backend only ever produces the first.
    """
    body = envelope(client.get("/api/v1/no-such-route"))

    assert "details" not in body


@pytest.mark.unit
def test_the_options_are_on():
    """The switch itself, so turning it off is a visible edit to this file."""
    assert ERROR_ENVELOPE_OPTIONS == {
        "error_codes": True,
        "validation_details": True,
    }


@pytest.mark.unit
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_every_deployed_domain_renders_the_code(domain):
    """Root B, per domain, not just root A.

    The four domain functions are what serve production; root A is what the
    suite and a local run use. They read the same dict, and this is what proves
    a domain application built on its own has the codes rather than only the
    mounted one the other tests exercise.
    """
    with TestClient(build_domain_app(DOMAINS[domain])) as test_client:
        response = test_client.get("/no-such-route-in-any-domain")

    assert response.status_code == 404
    assert envelope(response)["error_code"] == "NOT_FOUND"
