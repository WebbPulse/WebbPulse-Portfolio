"""The `X-WebbPulse-Domain` response header, which is how a cut is verified."""

import pytest
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.middleware import (
    DOMAIN_HEADER,
    MONOLITH_DOMAIN,
    DomainHeaderMiddleware,
)


def _bare_app(domain: str) -> Starlette:
    """A Starlette app with nothing but the middleware under test."""

    async def ok(_request):
        """Route returning 200."""
        return PlainTextResponse("ok")

    async def boom(_request):
        """Route raising an unhandled error."""
        raise RuntimeError("boom")

    async def down(_request):
        """Route raising a handled 503."""
        raise HTTPException(status_code=503, detail="down")

    app = Starlette(
        routes=[Route("/ok", ok), Route("/boom", boom), Route("/down", down)]
    )
    app.add_middleware(DomainHeaderMiddleware, domain=domain)
    return app


def test_header_is_set_on_a_normal_response():
    """A 200 carries the domain header naming the function."""
    with TestClient(_bare_app("public")) as client:
        response = client.get("/ok")
    assert response.status_code == 200
    assert response.headers[DOMAIN_HEADER] == "public"


def test_header_is_set_on_a_handled_error_and_on_a_404():
    """Anything the application itself returns names the function."""
    client = TestClient(_bare_app("public"), raise_server_exceptions=False)

    handled = client.get("/down")
    assert handled.status_code == 503
    assert handled.headers[DOMAIN_HEADER] == "public"

    missing = client.get("/no-such-path")
    assert missing.status_code == 404
    assert missing.headers[DOMAIN_HEADER] == "public"


def test_an_unhandled_exception_is_starlettes_and_carries_no_header():
    """The documented boundary, asserted so it cannot change unnoticed."""
    client = TestClient(_bare_app("public"), raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    assert DOMAIN_HEADER not in response.headers


def test_the_header_is_set_exactly_once():
    """Appended, not replaced, so a duplicate would be a silent ambiguity."""
    with TestClient(_bare_app("public")) as client:
        response = client.get("/ok")
    values = [v for k, v in response.headers.multi_items() if k == DOMAIN_HEADER]
    assert values == ["public"]


def test_a_non_http_scope_passes_straight_through():
    """A lifespan scope reaches the inner application untouched."""
    seen = []

    async def inner(scope, receive, send):
        """Minimal ASGI app that records the scope types it is called with."""
        seen.append(scope["type"])
        if scope["type"] != "lifespan":  # pragma: no cover - defensive
            return
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    with TestClient(DomainHeaderMiddleware(inner, domain="public")):
        pass

    assert seen == ["lifespan"]


@pytest.mark.parametrize("domain", ["content", "resume", "identity", "public"])
def test_each_domain_application_reports_its_own_name(domain):
    """Root B stamps the domain name, which is the whole point of the header."""
    from app.composition.wiring import build_domain_app

    app = build_domain_app(domain)
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.headers[DOMAIN_HEADER] == domain


def test_the_whole_surface_root_reports_monolith():
    """Root A reports a value that is not any one domain's name."""
    from app.composition.app import build_app

    with TestClient(build_app()) as client:
        response = client.get("/openapi.json")
    assert response.headers[DOMAIN_HEADER] == MONOLITH_DOMAIN


def test_the_monolith_value_is_not_a_domain_name():
    """`monolith` must never collide with a domain, or the signal inverts."""
    from app.composition.wiring import DOMAIN_NAMES

    assert MONOLITH_DOMAIN not in DOMAIN_NAMES
