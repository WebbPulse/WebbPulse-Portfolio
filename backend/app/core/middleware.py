"""ASGI middleware shared by every composition root: slash tolerance,
first-request seeding, request logging and the serving-domain header.
"""

import time

from starlette.routing import Match

from .logging import logger


class TrailingSlashMiddleware:
    """Serve a path whose trailing slash does not match any declared route."""

    def __init__(self, app, router):
        """Wrap `app`, matching candidate paths against `router`."""
        self.app = app
        self.router = router

    def _matches(self, scope):
        """Whether any route in the router matches this scope's path."""
        for route in self.router.routes:
            match, _ = route.matches(scope)
            if match != Match.NONE:
                return True
        return False

    async def __call__(self, scope, receive, send):
        """Rewrite the scope's path to its matching alternate, then pass it on."""
        if scope["type"] == "http" and not self._matches(scope):
            path = scope["path"]
            alternate = path[:-1] if path.endswith("/") and path != "/" else path + "/"
            if self._matches({**scope, "path": alternate}):
                scope["path"] = alternate
                scope["raw_path"] = alternate.encode("utf-8")
        await self.app(scope, receive, send)


#: One-slot cache for `_admin_credential_store`. A dict rather than a global so
#: "not looked up yet" is distinguishable from "looked up, and there is none".
_ADMIN_CREDENTIAL_STORE: dict = {}


def _admin_credential_store():
    """The identity credential store, when this deployment has one.

    `None` when `IDENTITY_ISSUER` is unset, so the seeder is in identity mode
    exactly when the identity flows are served. Cached for the process.
    """
    if "store" in _ADMIN_CREDENTIAL_STORE:
        return _ADMIN_CREDENTIAL_STORE["store"]

    from ..config import settings

    store = None
    if settings.IDENTITY_ISSUER:
        from webbpulse.dynamodb import Repository
        from webbpulse.identity import DynamoCredentialStore

        from ..db.tables import CREDENTIALS

        store = DynamoCredentialStore(
            Repository(
                CREDENTIALS,
                prefix=settings.DYNAMODB_TABLE_PREFIX,
                endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
            )
        )
    _ADMIN_CREDENTIAL_STORE["store"] = store
    return store


def reset_admin_credential_store() -> None:
    """Drop the cached store, so a test can change the environment underneath it."""
    _ADMIN_CREDENTIAL_STORE.clear()


def _seed_admin() -> None:
    """Seed the administrator user, importing the identity domain lazily."""
    from ..domains.identity.service import ensure_admin_seeded

    ensure_admin_seeded(_admin_credential_store())


def _seed_site_content() -> None:
    """Seed the site content singleton, importing the content domain lazily."""
    from ..domains.content.service import ensure_site_content_seeded

    ensure_site_content_seeded()


#: Seeders by the name a `Domain` names on its descriptor. Each imports its own
#: domain inside the call, so naming a seed here imports no domain package.
SEEDERS = {
    "admin": _seed_admin,
    "site_content": _seed_site_content,
}


class SeedMiddleware:
    """Run the named seeders on the first request in a process.

    `seeds` defaults to all of them, which is what the whole-surface root wants.
    A per-domain application passes only the seeds for the tables it owns.
    """

    def __init__(self, app, seeds=None):
        """Wrap `app`, validating that every named seeder exists."""
        self.app = app
        self.seeds = tuple(SEEDERS) if seeds is None else tuple(seeds)
        unknown = [name for name in self.seeds if name not in SEEDERS]
        if unknown:
            raise ValueError(f"Unknown seed(s): {', '.join(sorted(unknown))}")

    async def __call__(self, scope, receive, send):
        """Run this application's seeders, then pass the request on."""
        if scope["type"] == "http":
            for name in self.seeds:
                SEEDERS[name]()
        await self.app(scope, receive, send)


class RequestLoggingMiddleware:
    """Log one structured line per request with its status and duration."""

    def __init__(self, app):
        """Wrap `app`."""
        self.app = app

    async def __call__(self, scope, receive, send):
        """Time the request and log its outcome, however it ends."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": None}

        async def send_wrapper(message):
            """Capture the response status as it goes out."""
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status["code"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )


#: Response header naming the application that served the request, so which
#: function answered is readable from the response rather than from CloudWatch.
DOMAIN_HEADER = "x-webbpulse-domain"

#: What the whole-surface root reports, since no single domain name is true of
#: it. Distinguishes a local whole-surface response from a domain function's.
MONOLITH_DOMAIN = "monolith"


class DomainHeaderMiddleware:
    """Stamp every response with the name of the application that produced it.

    Written on `http.response.start`, so it lands on the error envelopes too.
    """

    def __init__(self, app, domain: str):
        """Wrap `app`, stamping responses with `domain`."""
        self.app = app
        self.value = domain.encode("latin-1")

    async def __call__(self, scope, receive, send):
        """Add the domain header to the outgoing response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            """Append the domain header as the response starts."""
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((DOMAIN_HEADER.encode("latin-1"), self.value))
            await send(message)

        await self.app(scope, receive, send_wrapper)
