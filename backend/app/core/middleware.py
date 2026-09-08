import time

from starlette.routing import Match

from .logging import logger


class TrailingSlashMiddleware:
    def __init__(self, app, router):
        self.app = app
        self.router = router

    def _matches(self, scope):
        for route in self.router.routes:
            match, _ = route.matches(scope)
            if match != Match.NONE:
                return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self._matches(scope):
            path = scope["path"]
            alternate = path[:-1] if path.endswith("/") and path != "/" else path + "/"
            if self._matches({**scope, "path": alternate}):
                scope["path"] = alternate
                scope["raw_path"] = alternate.encode("utf-8")
        await self.app(scope, receive, send)


class SeedMiddleware:
    """Seed the admin user and the site-content singleton on the first request.

    The two seeders are imported inside `__call__`, not at module scope, and
    that placement is load-bearing rather than stylistic. This module also holds
    `TrailingSlashMiddleware`, which every domain application adds, so a
    module-level import of `app.domains.content` and `app.domains.identity`
    would pull both domains into all four images. The `public` function would
    then carry `content`'s modules, pay their import on every cold start, and
    make the "no file under `domains/<name>/` reaches another domain" rule true
    only of the domain packages and not of what actually ships.

    The import is cached by `sys.modules` after the first request, so the cost
    is a dictionary lookup per request rather than a re-import.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from ..domains.content.service import ensure_site_content_seeded
            from ..domains.identity.service import ensure_admin_seeded

            ensure_admin_seeded()
            ensure_site_content_seeded()
        await self.app(scope, receive, send)


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": None}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status["code"],
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )


#: Response header naming the application that served the request. Section 6 of
#: docs/migration/pilot-split-plan.md verifies a route flip by confirming the
#: request reached the new function rather than falling through to $default on
#: the monolith, and the access log's routeKey answers that only for someone who
#: can read CloudWatch. This header answers it from the response itself, which is
#: what scripts/verify_route_cut.sh asserts on.
DOMAIN_HEADER = "x-webbpulse-domain"

#: What the whole-surface root reports. `app.composition.app` is every domain's
#: routers on one application, so no single domain name is true of it. The name
#: is historical: it is the value the deployed monolith reported, and during the
#: four cuts seeing it on a path meant the request had fallen through to
#: $default. Nothing deploys it now, and it is kept because it is still what
#: distinguishes a response from the local whole-surface app from one a real
#: domain function produced.
MONOLITH_DOMAIN = "monolith"


class DomainHeaderMiddleware:
    """Stamp every response with the name of the application that produced it.

    The value is the domain name for a per-domain function (`public`, `resume`,
    `content`, `identity`) and `monolith` for root A, so a response tells you
    which application served it without reading a log group. During the
    strangler that was the difference between a route flip that worked and one
    that silently did nothing; now it is what `scripts/verify_route_cut.sh`
    reads to confirm each path is served by the function that owns it.

    Written on `http.response.start`, so it lands on every response including
    the error envelopes, and it is a pure ASGI middleware for the same reason
    the others here are: it has to sit inside whatever `create_app` installed.
    """

    def __init__(self, app, domain: str):
        self.app = app
        self.value = domain.encode("latin-1")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                # A list of (name, value) byte pairs, lowercase by convention.
                # Appending rather than replacing is safe here because nothing
                # else in the stack sets this name.
                headers.append((DOMAIN_HEADER.encode("latin-1"), self.value))
            await send(message)

        await self.app(scope, receive, send_wrapper)
