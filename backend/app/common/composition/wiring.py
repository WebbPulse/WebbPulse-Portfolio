"""Portfolio's domain registry and the builder both composition roots go through.

The descriptor, the builder, the entrypoint pair, tracing and the local authorizer come
from `webbpulse.composition`. What stays here is Portfolio's own: the four registry rows,
the seed middleware, the trailing slash and domain header middleware, and the stricter
secrets check that also refuses to start in staging.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Sequence

from webbpulse import composition

from ..version import VERSION
from .settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import APIRouter, FastAPI

API_PREFIX = "/api/v1"

ERROR_ENVELOPE = "detailed"
"""Error envelope shape shared by both composition roots, so the same failure
renders the same body whichever root served it. The named shape implies the
`error_codes` and `validation_details` options it replaced, and drops the legacy
top-level `errors` key from a 422."""

SERVICE_NAME_TEMPLATE = "webbpulse-portfolio-{domain}"
"""Service name pattern. Terraform sets `SERVICE_NAME` to the same string, which
becomes the OpenTelemetry `service.name` and the `service` log field."""

ENFORCED_ENVIRONMENTS = ("staging", "production")
"""Environments where a missing secret is a startup failure rather than a warning.
Elsewhere a checkout with no AWS has to stay runnable."""


class Domain(composition.Domain):
    """The shared descriptor, plus the seeders Portfolio keeps in `metadata`."""

    @property
    def seeds(self) -> tuple[str, ...]:
        """Seeders the domain runs on the first request, by the names in
        `app.common.core.middleware.SEEDERS`. A domain seeds only the tables it owns."""
        return tuple(self.metadata.get("seeds", ()))


def _content_routers() -> "list[APIRouter]":
    """Import and return the content domain's routers."""
    from app.domains.content.router import router

    return [router]


def _resume_routers() -> "list[APIRouter]":
    """Import and return the resume domain's routers."""
    from app.domains.resume.router import router

    return [router]


def _identity_routers() -> "list[APIRouter]":
    """Import and return the identity domain's routers."""
    from app.domains.identity.router import router

    return [router]


def _identity_unprefixed_routers(settings: Settings) -> "list[APIRouter]":
    """The shared package's identity router, when this deployment configures one.

    Empty when `IDENTITY_ISSUER` is unset, so a deployment without an issuer
    builds none of the glue's AWS clients.
    """
    if not settings.IDENTITY_ISSUER:
        return []

    from app.domains.identity.package_glue import build_router

    return [build_router(settings)]


def _public_routers() -> "list[APIRouter]":
    """Import and return the public domain's routers."""
    from app.domains.public.router import router

    return [router]


DOMAINS = composition.DomainRegistry(
    [
        Domain(
            name="content",
            title="WebbPulse Portfolio content",
            load_routers=_content_routers,
            router_prefix=API_PREFIX,
            service_name_template=SERVICE_NAME_TEMPLATE,
            requires_secrets=("SECRET_KEY",),
            metadata={"seeds": ("site_content",)},
        ),
        Domain(
            name="resume",
            title="WebbPulse Portfolio resume",
            load_routers=_resume_routers,
            router_prefix=API_PREFIX,
            service_name_template=SERVICE_NAME_TEMPLATE,
            requires_secrets=("SECRET_KEY",),
        ),
        Domain(
            name="identity",
            title="WebbPulse Portfolio identity",
            load_routers=_identity_routers,
            load_unprefixed_routers=_identity_unprefixed_routers,
            router_prefix=f"{API_PREFIX}/admin",
            router_tags=("admin",),
            service_name_template=SERVICE_NAME_TEMPLATE,
            requires_secrets=(
                "SECRET_KEY",
                "ADMIN_USERNAME",
                "ADMIN_PASSWORD",
                "ADMIN_EMAIL",
            ),
            metadata={"seeds": ("admin",)},
        ),
        Domain(
            name="public",
            title="WebbPulse Portfolio public",
            load_routers=_public_routers,
            router_prefix="",
            service_name_template=SERVICE_NAME_TEMPLATE,
        ),
    ]
)

DOMAIN_NAMES = DOMAINS.names


def check_required_secrets(domains: "Iterable[composition.Domain]", *, settings: Settings | None = None) -> None:
    """Fail fast on a missing secret, once at startup, per the domains served.

    The shared `check_secrets` with Portfolio's policy: strict in staging as well as
    production, and a warning for every missing name elsewhere rather than for
    `SECRET_KEY` alone. Resolution stays lazy, so a root serving no domain that names
    a secret makes no Secrets Manager call.
    """
    served = list(domains)
    resolved = settings if settings is not None else get_settings()
    composition.check_secrets(
        served,
        resolved,
        strict=resolved.environment in ENFORCED_ENVIRONMENTS,
        warn_on={name for domain in served for name in domain.requires_secrets},
    )


def check_domain_secrets(domain: composition.Domain, settings: Settings | None) -> None:
    """The `check` hook each entrypoint's `main` runs, over its one domain."""
    check_required_secrets([domain], settings=settings)


def add_seed_middleware(seeds: Sequence[str] | None):
    """A hook adding `SeedMiddleware` for these seeders, or for every seeder on `None`."""

    def hook(app: "FastAPI", domains: Sequence[composition.Domain]) -> None:
        """Run the seeders on the first request."""
        from ..core.middleware import SeedMiddleware

        if seeds is None:
            app.add_middleware(SeedMiddleware)
        elif seeds:
            app.add_middleware(SeedMiddleware, seeds=tuple(seeds))

    return hook


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
    seeds: Sequence[str] | None = (),
    **create_app_kwargs: Any,
) -> "FastAPI":
    """Both roots' builder: the shared `build_domain_app` with Portfolio's middleware.

    Middleware is added once every router is in and in the order it always was, seeds
    first, then `before_routing`, then trailing slash and the domain header outermost.
    """
    resolved = settings if settings is not None else get_settings()
    return composition.build_domain_app(
        domains,
        registry=DOMAINS,
        settings=resolved,
        after_routers=[
            add_seed_middleware(seeds),
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
        seeds=resolved_domain.metadata.get("seeds", ()),
        include_health=resolved_domain.name != "public",
    )
