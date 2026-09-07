"""The `X-WebbPulse-Domain` response header, which is how a cut is verified.

Section 6 of `docs/migration/pilot-split-plan.md` verifies a route flip by
confirming the request reached the new function instead of falling through to
`$default` on the monolith. The access log's `routeKey` answers that, but only
for someone who can read the log group and only after the log has been
delivered. This header answers it from the response itself, synchronously, which
is what `scripts/verify_route_cut.sh` asserts on.

Three properties:

- **Every per-domain application stamps its own name.** A response from the
  `public` function says `public`, so the script can tell it apart from a
  response the monolith produced for the same path.
- **Both whole-surface roots stamp `monolith`.** `app.main` is the deployed
  monolith and `app.composition.app` is the same surface built from the domain
  routers. Neither is one domain, and seeing `monolith` on a path that was
  supposed to be cut over is the signal that the flip did nothing.
- **The header survives a handled error and a 404.** A cut that answers 503 or
  404 still has to say which function answered, otherwise a broken image looks
  exactly like a route that never moved.

One boundary is worth stating because it is Starlette's and not ours.
`Starlette.build_middleware_stack` puts `ServerErrorMiddleware` outside every
user middleware unconditionally, so the bare 500 it synthesises for an
*unhandled* exception never passes through this middleware and carries no
header. That is not a gap the script has to work around: an unhandled 500 from
a route that was just cut over is a broken deployment either way, and the
absence of the header on a 500 is itself distinguishable from a monolith
response, which always carries `monolith`.
"""

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
    """A Starlette app with nothing but the middleware under test.

    Deliberately not built through `create_app`: this asserts the middleware's
    own behaviour, including on the error path, without the shared package's
    handlers turning the exception into a 500 before the middleware sees it.
    """

    async def ok(request):
        return PlainTextResponse("ok")

    async def boom(request):
        raise RuntimeError("boom")

    async def down(request):
        raise HTTPException(status_code=503, detail="down")

    app = Starlette(
        routes=[Route("/ok", ok), Route("/boom", boom), Route("/down", down)]
    )
    app.add_middleware(DomainHeaderMiddleware, domain=domain)
    return app


def test_header_is_set_on_a_normal_response():
    with TestClient(_bare_app("public")) as client:
        response = client.get("/ok")
    assert response.status_code == 200
    assert response.headers[DOMAIN_HEADER] == "public"


def test_header_is_set_on_a_handled_error_and_on_a_404():
    """Anything the application itself returns names the function.

    `raise_server_exceptions=False` makes the client return the response
    Starlette generated rather than re-raising, which is what a real caller
    behind API Gateway sees.
    """
    client = TestClient(_bare_app("public"), raise_server_exceptions=False)

    handled = client.get("/down")
    assert handled.status_code == 503
    assert handled.headers[DOMAIN_HEADER] == "public"

    missing = client.get("/no-such-path")
    assert missing.status_code == 404
    assert missing.headers[DOMAIN_HEADER] == "public"


def test_an_unhandled_exception_is_starlettes_and_carries_no_header():
    """The documented boundary, asserted so it cannot change unnoticed.

    `ServerErrorMiddleware` is built outside every user middleware, so the 500
    it synthesises for an unhandled exception does not pass through this one.
    Pinning it here means a future Starlette that moves the boundary shows up as
    a failing test rather than as a verification script that quietly starts
    depending on a header it will not always get.
    """
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


def test_header_is_not_set_on_a_non_http_scope():
    """A websocket scope passes straight through.

    The middleware only wraps `send` for `http`, so a lifespan or websocket
    scope must reach the inner application untouched rather than having a
    header appended to a message that has no headers.
    """
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    middleware = DomainHeaderMiddleware(inner, domain="public")

    async def receive():  # pragma: no cover - never awaited
        raise AssertionError("receive should not be called")

    async def send(message):  # pragma: no cover - never awaited
        raise AssertionError("send should not be called")

    import asyncio

    asyncio.run(middleware({"type": "lifespan"}, receive, send))
    assert seen == ["lifespan"]


@pytest.mark.parametrize("domain", ["content", "resume", "identity", "public"])
def test_each_domain_application_reports_its_own_name(domain):
    """Root B stamps the domain name, which is the whole point of the header."""
    from app.composition.wiring import build_domain_app

    app = build_domain_app(domain)
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.headers[DOMAIN_HEADER] == domain


def test_the_monolith_reports_monolith():
    """Both whole-surface roots report the same non-domain value.

    `app.main` is what serves `$default` until the last cut, so this is the
    value the verification script treats as "not cut over yet".
    """
    from app.composition.app import build_app
    from app.main import app as deployed_monolith

    with TestClient(deployed_monolith) as client:
        response = client.get("/openapi.json")
    assert response.headers[DOMAIN_HEADER] == MONOLITH_DOMAIN

    with TestClient(build_app()) as client:
        response = client.get("/openapi.json")
    assert response.headers[DOMAIN_HEADER] == MONOLITH_DOMAIN


def test_the_monolith_value_is_not_a_domain_name():
    """`monolith` must never collide with a domain, or the signal inverts."""
    from app.composition.wiring import DOMAIN_NAMES

    assert MONOLITH_DOMAIN not in DOMAIN_NAMES
