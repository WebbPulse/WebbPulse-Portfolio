import time

from starlette.routing import Match

from .admin import ensure_admin_seeded
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


class AdminSeedMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            ensure_admin_seeded()
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
