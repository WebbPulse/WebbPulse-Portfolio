"""Root A: every domain's routers on one application, in one process.

What the test suite and a local `uvicorn app.common.composition.app:app` run against.
Nothing deploys it; the four domain functions serve every route in production.

Both router kinds are mounted, exactly as `build_domain_app` mounts them for one
domain: the prefixed routers under the domain's prefix and the routers that declare
their own full paths at the root. The identity package's routes are the second kind,
so a root that mounted only the first would serve no login at all.

In the local environment the gateway's JWT authorizer is stood in for by
`LocalAuthorizerMiddleware`, since without it a valid token reaches every admin
route carrying no verified claims and each one answers 401.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from webbpulse.http import create_app

from ..core.middleware import (
    LOCAL_ENVIRONMENT,
    MONOLITH_DOMAIN,
    DomainHeaderMiddleware,
    LocalAuthorizerMiddleware,
    SeedMiddleware,
    TrailingSlashMiddleware,
)
from ..version import VERSION
from .settings import Settings, get_settings
from .wiring import DOMAINS, ERROR_ENVELOPE, check_required_secrets

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


def build_app(settings: Settings | None = None) -> "FastAPI":
    """Every domain's routers on one application.

    The include order is `wiring.DOMAINS`, so the `paths` map keeps the order
    the published document has always had.
    """
    resolved = settings if settings is not None else get_settings()

    check_required_secrets(DOMAINS.values(), settings=resolved)

    app = create_app(
        title=resolved.APP_NAME,
        version=VERSION,
        service_name="webbpulse-portfolio",
        settings=resolved,
        include_health=False,
        description="Blog API for Portfolio Website",
        redirect_slashes=False,
        error_envelope=ERROR_ENVELOPE,
    )

    for domain in DOMAINS.values():
        for router in domain.load_routers():
            app.include_router(
                router,
                prefix=domain.router_prefix,
                tags=list(domain.router_tags),
            )
        if domain.load_unprefixed_routers is None:
            continue
        for router in domain.load_unprefixed_routers(resolved):
            app.include_router(router)

    app.add_middleware(SeedMiddleware)
    if resolved.ENVIRONMENT.strip().lower() == LOCAL_ENVIRONMENT and resolved.IDENTITY_ISSUER:
        app.add_middleware(LocalAuthorizerMiddleware, environment=resolved.ENVIRONMENT)
    app.add_middleware(TrailingSlashMiddleware, router=app.router)
    app.add_middleware(DomainHeaderMiddleware, domain=MONOLITH_DOMAIN)
    return app


app = build_app()
