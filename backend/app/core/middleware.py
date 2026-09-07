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
