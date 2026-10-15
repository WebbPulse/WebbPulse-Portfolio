"""Portfolio's domain registry and the builder both composition roots go through.

The descriptor, the builder, the entrypoint pair and tracing come
from `webbpulse.composition`. What stays here is Portfolio's own: the registry row for the
public domain and the trailing slash and domain header middleware. The public domain
names no secret, so the shared startup check has nothing to require.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from webbpulse import composition

from ..version import VERSION
from .settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import APIRouter, FastAPI

ERROR_ENVELOPE = "detailed"
"""Error envelope shape shared by both composition roots, so the same failure
renders the same body whichever root served it. The named shape implies the
`error_codes` and `validation_details` options it replaced, and drops the legacy
top-level `errors` key from a 422."""

SERVICE_NAME_TEMPLATE = "webbpulse-portfolio-{domain}"
"""Service name pattern. Terraform sets `SERVICE_NAME` to the same string, which
becomes the OpenTelemetry `service.name` and the `service` log field."""


def _public_routers() -> "list[APIRouter]":
    """Import and return the public domain's routers."""
    from app.domains.public.router import router

    return [router]


DOMAINS = composition.DomainRegistry(
    [
        composition.Domain(
            name="public",
            title="WebbPulse Portfolio public",
            load_routers=_public_routers,
            router_prefix="",
            service_name_template=SERVICE_NAME_TEMPLATE,
        ),
    ]
)

DOMAIN_NAMES = DOMAINS.names


def add_routing_middleware(domain_header: str):
    """A hook adding trailing slash handling and the `X-WebbPulse-Domain` header."""

    def hook(app: "FastAPI", domains: Sequence[composition.Domain]) -> None:
        """Outermost middleware, added last, so every response carries the header."""
        from webbpulse.http import DomainHeaderMiddleware, TrailingSlashMiddleware

        app.add_middleware(TrailingSlashMiddleware, router=app.router)
        app.add_middleware(DomainHeaderMiddleware, domain=domain_header)

    return hook


def build(
    domains: "composition.Domain | str | Sequence[composition.Domain | str]",
    *,
    domain_header: str,
    settings: Settings | None = None,
    before_routing: Sequence[Any] = (),
    **create_app_kwargs: Any,
) -> "FastAPI":
    """Both roots' builder: the shared `build_domain_app` with Portfolio's middleware.

    Middleware is added once every router is in: `before_routing` first, then trailing
    slash and the domain header outermost.
    """
    resolved = settings if settings is not None else get_settings()
    return composition.build_domain_app(
        domains,
        registry=DOMAINS,
        settings=resolved,
        after_routers=[
            *before_routing,
            add_routing_middleware(domain_header),
        ],
        instrument=True,
        version=VERSION,
        redirect_slashes=False,
        error_envelope=ERROR_ENVELOPE,
        **create_app_kwargs,
    )


def build_domain_app(domain: composition.Domain | str, *, settings: Settings | None = None) -> "FastAPI":
    """Build one domain's application: root B's whole job.

    Both roots go through `build`, so the middleware stack is identical locally, in
    the suite and in each deployed function.
    """
    resolved_domain = DOMAINS[domain] if isinstance(domain, str) else domain
    return build(
        resolved_domain,
        settings=settings,
        domain_header=resolved_domain.name,
        include_health=resolved_domain.name != "public",
    )
