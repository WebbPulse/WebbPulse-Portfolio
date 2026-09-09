"""The request id reaches a log line, and the response echoes it.

This is the property the Powertools logger never had here. Its correlation is
`@logger.inject_lambda_context`, a decorator on a Lambda handler, and the four
domain functions run behind the Lambda Web Adapter, which turns each invoke into
an HTTP request against a uvicorn process rather than calling a handler. Nothing
was decorated, so nothing correlated, and every log line went to CloudWatch with
no request id on it at all.

`webbpulse.log_context` is what replaced it. `RequestIdMiddleware`, which
`create_app` has always mounted, binds a ContextVar for the life of the request,
and `webbpulse.logging.JsonFormatter` merges it into every record. The chain has
three links and each one is asserted separately below, because a test that only
checked the response header would pass with the log half of it entirely broken,
which is exactly the state this change is fixing.

The formatter is exercised rather than mocked. `caplog` captures a `LogRecord`
and says nothing about what reaches CloudWatch, and the merge being tested lives
in `JsonFormatter.format`, so these tests format a real record through a real
formatter and parse the JSON line that comes out. That is the artifact a Logs
Insights query reads.
"""

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
    """Capture every record the application logs, as parsed JSON objects.

    A handler on the root logger with the real `JsonFormatter`, so what is
    collected is the line CloudWatch would receive rather than a `LogRecord`
    that still has to survive formatting. The level is forced to DEBUG for the
    duration: `tests/conftest.py` sets `LOG_LEVEL=WARNING`, which would drop
    every `logger.info` these tests are written against.
    """
    lines: list[dict] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
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
    """An inbound `X-Request-ID` is honoured, logged and echoed.

    One value asserted in both places, which is the whole point: a caller that
    put an id on the request can find that request's log lines by the id it
    chose, and the two halves cannot drift because they are the same string.
    """
    incoming = "portfolio-test-request-id"

    @client.app.get("/_test/log")
    def _log_something() -> dict:
        logger.info("handled a request")
        return {"ok": True}

    response = client.get("/_test/log", headers={REQUEST_ID_HEADER: incoming})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == incoming

    logged = [line for line in json_lines if line["message"] == "handled a request"]
    assert len(logged) == 1
    assert logged[0]["request_id"] == incoming
    # The rest of the shape CarModPicker also emits, since both products format
    # through the same class. A saved Logs Insights query reads both log groups.
    assert logged[0]["level"] == "INFO"
    assert logged[0]["service"] == "webbpulse-portfolio"
    assert logged[0]["environment"] == "test"
    assert logged[0]["logger"] == "app"
    assert logged[0]["timestamp"].endswith("Z")


def test_a_generated_request_id_is_used_when_the_caller_sends_none(client, json_lines):
    """With no inbound header the middleware mints a UUID4, and it still matches.

    The generated case is the one that runs in production, because nothing in
    front of these functions sets the header today. Asserting only the inbound
    case would leave the default path untested.
    """

    @client.app.get("/_test/generated")
    def _log_something() -> dict:
        logger.info("generated id")
        return {"ok": True}

    response = client.get("/_test/generated")

    echoed = response.headers[REQUEST_ID_HEADER]
    # A UUID4, not the `"-"` placeholder and not an empty string.
    assert uuid.UUID(echoed).version == 4

    logged = [line for line in json_lines if line["message"] == "generated id"]
    assert len(logged) == 1
    assert logged[0]["request_id"] == echoed


def test_an_empty_inbound_header_is_replaced_rather_than_propagated(client):
    """A blank `X-Request-ID` gets a generated id, not a blank one.

    A header a caller sent as whitespace would otherwise become the correlation
    id for the request, which is indistinguishable from no id at all in a log
    group and would make one grep match every such request.
    """
    response = client.get("/health", headers={REQUEST_ID_HEADER: "   "})

    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed.strip()
    assert uuid.UUID(echoed).version == 4


def test_the_context_does_not_leak_between_requests(client):
    """Nothing is bound before a request or after one.

    `RequestIdMiddleware` resets its token in a `finally`, and this pins that
    rather than trusting it. A leaked id would attribute one caller's log lines
    to the previous caller, which is worse than having no id, because it looks
    correct.
    """
    assert request_id_var.get() == UNSET

    client.get("/health", headers={REQUEST_ID_HEADER: "first"})
    assert request_id_var.get() == UNSET

    client.get("/health", headers={REQUEST_ID_HEADER: "second"})
    assert request_id_var.get() == UNSET


def test_an_authenticated_request_logs_the_user_id(
    client, json_lines, admin_auth_headers, test_admin_user
):
    """`CurrentUser` binds `user_id`, and it lands on the log line.

    The request id arrives from the middleware and the user id from the
    authentication dependency, so this is the assertion that the second half is
    wired: a log line emitted after authentication carries both.

    The dependency is `CurrentUser`, the name every route takes, rather than the
    `get_current_user` resolver underneath it. As of webbpulse 0.8.0 the binding
    is `webbpulse.http.user_id_dependency` wrapping that resolver, so the
    resolver alone binds nothing and testing it would assert the wrong half.

    **The route below is deliberately `def`, not `async def`.** That is the
    shape that used to lose the binding: a sync dependency runs through
    `anyio.to_thread.run_sync`, which copies the context into a worker thread and
    discards the copy on return. The package binds in its own async wrapper
    after the value has crossed that boundary, so a sync route handler still sees
    it, and keeping this one sync is what pins that rather than trusting it.

    The route is declared here rather than borrowed from a domain, because no
    existing authenticated route logs anything. Borrowing one would assert that
    the dependency ran, which every `tests/test_auth_*` module already covers,
    and say nothing about whether the binding reaches a record. This route
    depends on the real dependency and then logs, which is the actual path a
    domain service takes.
    """

    @client.app.get("/_test/authenticated")
    def _log_something(current_user: dict = Depends(CurrentUser)) -> dict:
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
    """An anonymous request carries the placeholder rather than a stale user.

    `current_context` omits an unset field, so `user_id` is an absent key rather
    than a null one, which is what keeps a metric filter on it meaningful.
    """

    @client.app.get("/_test/anonymous")
    def _log_something() -> dict:
        logger.info("anonymous request")
        return {"ok": True}

    client.get("/_test/anonymous")

    logged = [line for line in json_lines if line["message"] == "anonymous request"]
    assert len(logged) == 1
    assert "user_id" not in logged[0]
    assert user_id_var.get() == UNSET


def test_extra_fields_become_top_level_keys(client, json_lines):
    """The `extra={...}` form replaces Powertools' keyword arguments faithfully.

    Every call site that passed `logger.info("msg", key=value)` now passes
    `extra={"key": value}`, and this pins that the emitted object is the same
    shape it was: the field is a top-level key, not nested and not dropped.
    `logging.Logger` raises on the keyword form, so a missed call site is a
    500 rather than a silently thinner log line, but the conversion is worth an
    assertion on the output rather than only on the absence of a crash.
    """

    @client.app.get("/_test/extra")
    def _log_something() -> dict:
        logger.info("with fields", extra={"duration_ms": 12.5, "status": 200})
        return {"ok": True}

    client.get("/_test/extra")

    logged = [line for line in json_lines if line["message"] == "with fields"]
    assert len(logged) == 1
    assert logged[0]["duration_ms"] == 12.5
    assert logged[0]["status"] == 200
