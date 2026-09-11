"""Root A: every domain's routers on one application, in one process.

What the test suite and a local `uvicorn app.composition.app:app` run against.
Nothing deploys it; the four domain functions serve every route in production.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from webbpulse.http import create_app

from ..core.middleware import (
    MONOLITH_DOMAIN,
    DomainHeaderMiddleware,
    SeedMiddleware,
    TrailingSlashMiddleware,
)
from ..version import VERSION
from .settings import Settings, get_settings
from .wiring import DOMAINS, ERROR_ENVELOPE_OPTIONS, check_required_secrets

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
        **ERROR_ENVELOPE_OPTIONS,
    )

    for domain in DOMAINS.values():
        for router in domain.load_routers():
            app.include_router(
                router,
                prefix=domain.router_prefix,
                tags=list(domain.router_tags),
            )

    app.add_middleware(SeedMiddleware)
    app.add_middleware(TrailingSlashMiddleware, router=app.router)
    app.add_middleware(DomainHeaderMiddleware, domain=MONOLITH_DOMAIN)
    return app


app = build_app()
