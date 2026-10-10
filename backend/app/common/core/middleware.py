"""First-request seeding, the middleware every composition root adds beside the
shared `webbpulse.http` slash tolerance and serving-domain header.
"""

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
