"""Root A: every domain's routers on one application, in one process.

What the test suite and a local `uvicorn app.common.composition.app:app` run against.
Nothing deploys it; the public function serves every route in production.

It goes through the same `wiring.build` as the function, so the routers are mounted
exactly as they are for one domain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from webbpulse.http import MONOLITH_DOMAIN

from .settings import Settings, get_settings
from .wiring import DOMAINS, build

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


def build_app(settings: Settings | None = None) -> "FastAPI":
    """Every domain's routers on one application, in `wiring.DOMAINS` order."""
    resolved = settings if settings is not None else get_settings()

    return build(
        list(DOMAINS.values()),
        settings=resolved,
        domain_header=MONOLITH_DOMAIN,
        title=resolved.APP_NAME,
        service_name="webbpulse-portfolio",
        include_health=False,
        description="Public API for the Portfolio website",
    )


app = build_app()
