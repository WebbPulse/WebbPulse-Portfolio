"""The request id reaches a log line, and the response echoes it."""

import json
import logging
import uuid

import pytest
from fastapi import Depends
from webbpulse.http import REQUEST_ID_HEADER
from webbpulse.log_context import UNSET, request_id_var, user_id_var
from webbpulse.logging import JsonFormatter

from app.core.logging import logger
from app.core.security import CurrentUser


@pytest.fixture
def json_lines(monkeypatch):
    """Capture every record the application logs, as parsed JSON objects."""
    lines: list[dict] = []

    class Collector(logging.Handler):
        """Logging handler that parses each formatted record into the captured list."""

        def emit(self, record: logging.LogRecord) -> None:
            """Append the formatted record, parsed as JSON."""
            lines.append(json.loads(self.format(record)))

    handler = Collector()
    handler.setFormatter(
        JsonFormatter(service="webbpulse-portfolio", environment="test")
    )
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


def test_incoming_request_id_reaches_a_log_line_and_the_response(client, json_lines):
    """An inbound `X-Request-ID` is honoured, logged and echoed."""
    incoming = "portfolio-test-request-id"

    @client.app.get("/_test/log")
    def _log_something() -> dict:
        """Route that logs one line so the captured records can be inspected."""
        logger.info("handled a request")
        return {"ok": True}

    response = client.get("/_test/log", headers={REQUEST_ID_HEADER: incoming})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == incoming

    logged = [line for line in json_lines if line["message"] == "handled a request"]
    assert len(logged) == 1
    assert logged[0]["request_id"] == incoming
    assert logged[0]["level"] == "INFO"
    assert logged[0]["service"] == "webbpulse-portfolio"
    assert logged[0]["environment"] == "test"
    assert logged[0]["logger"] == "app"
    assert logged[0]["timestamp"].endswith("Z")


def test_a_generated_request_id_is_used_when_the_caller_sends_none(client, json_lines):
    """With no inbound header the middleware mints a UUID4, and it still matches."""

    @client.app.get("/_test/generated")
    def _log_something() -> dict:
        """Route that logs one line so the captured records can be inspected."""
        logger.info("generated id")
        return {"ok": True}

    response = client.get("/_test/generated")

    echoed = response.headers[REQUEST_ID_HEADER]
    assert uuid.UUID(echoed).version == 4

    logged = [line for line in json_lines if line["message"] == "generated id"]
    assert len(logged) == 1
    assert logged[0]["request_id"] == echoed


def test_an_empty_inbound_header_is_replaced_rather_than_propagated(client):
    """A blank `X-Request-ID` gets a generated id, not a blank one."""
    response = client.get("/health", headers={REQUEST_ID_HEADER: "   "})

    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed.strip()
    assert uuid.UUID(echoed).version == 4


def test_the_context_does_not_leak_between_requests(client):
    """Nothing is bound before a request or after one."""
    assert request_id_var.get() == UNSET

    client.get("/health", headers={REQUEST_ID_HEADER: "first"})
    assert request_id_var.get() == UNSET

    client.get("/health", headers={REQUEST_ID_HEADER: "second"})
    assert request_id_var.get() == UNSET


def test_an_authenticated_request_logs_the_user_id(
    client, json_lines, admin_auth_headers, test_admin_user
):
    """`CurrentUser` binds `user_id`, and it lands on the log line."""

    @client.app.get("/_test/authenticated")
    def _log_something(current_user: dict = Depends(CurrentUser)) -> dict:
        """Route that logs one line as an authenticated caller."""
        logger.info("authenticated request")
        return {"ok": True}

    response = client.get("/_test/authenticated", headers=admin_auth_headers)
    assert response.status_code == 200

    request_id = response.headers[REQUEST_ID_HEADER]
    logged = [line for line in json_lines if line["message"] == "authenticated request"]
    assert len(logged) == 1
    assert logged[0]["request_id"] == request_id
    assert logged[0]["user_id"] == str(test_admin_user["id"])


def test_an_unauthenticated_request_has_no_user_id(client, json_lines):
    """An anonymous request carries the placeholder rather than a stale user."""

    @client.app.get("/_test/anonymous")
    def _log_something() -> dict:
        """Route that logs one line as an anonymous caller."""
        logger.info("anonymous request")
        return {"ok": True}

    client.get("/_test/anonymous")

    logged = [line for line in json_lines if line["message"] == "anonymous request"]
    assert len(logged) == 1
    assert "user_id" not in logged[0]
    assert user_id_var.get() == UNSET


def test_extra_fields_become_top_level_keys(client, json_lines):
    """The `extra={...}` form replaces Powertools' keyword arguments faithfully."""

    @client.app.get("/_test/extra")
    def _log_something() -> dict:
        """Route that logs one line carrying extra fields."""
        logger.info("with fields", extra={"duration_ms": 12.5, "status": 200})
        return {"ok": True}

    client.get("/_test/extra")

    logged = [line for line in json_lines if line["message"] == "with fields"]
    assert len(logged) == 1
    assert logged[0]["duration_ms"] == 12.5
    assert logged[0]["status"] == 200
