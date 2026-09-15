"""ASGI middleware shared by every composition root: slash tolerance,
first-request seeding, the serving-domain header and the local authorizer.
"""

import json

from starlette.routing import Match


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


_ADMIN_CREDENTIAL_STORE: dict = {}
"""One-slot cache for `_admin_credential_store`. A dict rather than a global so "not
looked up yet" is distinguishable from "looked up, and there is none"."""


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
    from app.domains.identity.service import ensure_admin_seeded

    ensure_admin_seeded(_admin_credential_store())


def _seed_site_content() -> None:
    """Seed the site content singleton, importing the content domain lazily."""
    from app.domains.content.service import ensure_site_content_seeded

    ensure_site_content_seeded()


SEEDERS = {
    "admin": _seed_admin,
    "site_content": _seed_site_content,
}
"""Seeders by the name a `Domain` names on its descriptor. Each imports its own
domain inside the call, so naming a seed here imports no domain package."""


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


LOCAL_ENVIRONMENT = "local"
"""The only `ENVIRONMENT` value `LocalAuthorizerMiddleware` will run under."""

REQUEST_CONTEXT_HEADER = b"x-amzn-request-context"
"""The header API Gateway's Lambda Web Adapter injects, carrying the authorizer's
verified claims. Lower case bytes, which is the spelling an ASGI scope holds."""


class _InProcessKeyClient:
    """Resolves a token's `kid` against a JWKS held in memory.

    `JwksVerifier` would otherwise fetch the key set over HTTP, and on a local stack
    the issuer it would fetch from is this very process, so the request would block
    the event loop waiting on itself. The key set is the one the local signer derives,
    so it is the same document the JWKS route serves without going through it.
    """

    def __init__(self, jwks):
        """Index the key set by `kid`."""
        from jwt import PyJWK

        self._keys = {key["kid"]: PyJWK(key) for key in jwks.get("keys", []) if key.get("kid")}

    def get_signing_key_from_jwt(self, token):
        """The key whose `kid` matches this token's header, raising when none does."""
        import jwt

        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self._keys:
            raise KeyError(f"no key in the local JWKS carries kid {kid!r}")
        return self._keys[kid]


class LocalAuthorizerMiddleware:
    """Stand in for the API Gateway JWT authorizer on a stack with no gateway.

    Deployed, the gateway verifies the access token and the adapter hands the
    function its claims in `x-amzn-request-context`; every admin route reads them
    through `identity_subject`. A local stack has no gateway, so a perfectly valid
    token reaches the app carrying no claims and every write answers 401. This
    verifies the token in process against the local signer's own key set and
    publishes the result in the shape the reader expects.

    Constructing it outside the local environment raises, so no deployment can
    reach a path where a request is authorized by anything but the gateway. Any
    inbound copy of the header is dropped before verification, so a caller can
    never present claims of its own.
    """

    def __init__(self, app, environment: str):
        """Wrap `app`, refusing any environment but the local one."""
        self.app = app
        if environment.strip().lower() != LOCAL_ENVIRONMENT:
            raise ValueError(
                f"LocalAuthorizerMiddleware refuses environment {environment!r}. It "
                "verifies tokens in process, which must never stand in for the "
                "gateway's own authorizer in a deployed environment."
            )
        self._verifier = None

    def _build_verifier(self):
        """A verifier reading the key set this process signs with, fetching nothing."""
        from webbpulse.identity import IdentitySettings, JwksVerifier
        from webbpulse.identity.local_signer import signing_client
        from webbpulse.identity.service import TokenService

        settings = IdentitySettings()  # pyright: ignore[reportCallIssue]
        jwks = TokenService(settings, signing_client(settings)).jwks()
        return JwksVerifier.from_settings(settings, client=_InProcessKeyClient(jwks))

    def _verify(self, token: str):
        """This token's claims, or `None` when it is not one this issuer signed."""
        from webbpulse.identity import InvalidToken

        if self._verifier is None:
            self._verifier = self._build_verifier()
        try:
            return self._verifier.verify(token)
        except InvalidToken:
            return None

    async def __call__(self, scope, receive, send):
        """Replace the request context header with the claims this token carries."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = [(name, value) for name, value in scope["headers"] if name != REQUEST_CONTEXT_HEADER]
        token = ""
        for name, value in headers:
            if name != b"authorization":
                continue
            scheme, _, rest = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer":
                token = rest.strip()
            break

        claims = self._verify(token) if token else None
        if claims is not None:
            context = json.dumps({"authorizer": {"jwt": {"claims": claims}}})
            headers.append((REQUEST_CONTEXT_HEADER, context.encode("latin-1")))

        await self.app({**scope, "headers": headers}, receive, send)


DOMAIN_HEADER = "x-webbpulse-domain"
"""Response header naming the application that served the request, so which function
answered is readable from the response rather than from CloudWatch."""

MONOLITH_DOMAIN = "monolith"
"""What the whole-surface root reports, since no single domain name is true of it.
Distinguishes a local whole-surface response from a domain function's."""


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
