"""Domain descriptors and the builder that turns one into an application.

Both composition roots read this map, so a mounted application and a deployed
function cannot drift apart.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable

from webbpulse.http import create_app

from ..version import VERSION
from .settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import APIRouter, FastAPI

API_PREFIX = "/api/v1"

ERROR_ENVELOPE_OPTIONS: dict[str, bool] = {
    "error_codes": True,
    "validation_details": True,
}
"""Error envelope options shared by both composition roots, so the same failure
renders the same body whichever root served it."""

SERVICE_NAME_TEMPLATE = "webbpulse-portfolio-{domain}"
"""Service name pattern. Terraform sets `SERVICE_NAME` to the same string, which
becomes the OpenTelemetry `service.name` and the `service` log field."""


@dataclass(frozen=True)
class Domain:
    """One deployable domain."""

    name: str
    title: str
    load_routers: Callable[[], "list[APIRouter]"]
    """Called lazily so importing this module imports no domain package."""
    router_prefix: str = API_PREFIX
    """Where the domain's routers mount, so both roots supply the same prefix."""
    router_tags: tuple[str, ...] = ()
    """Tags applied when the routers mount, shared by both roots."""
    requires_secrets: tuple[str, ...] = ()
    """Secret fields the domain cannot serve a request without. A domain naming none
    needs no `secretsmanager:GetSecretValue` grant."""
    seeds: tuple[str, ...] = ()
    """Seeders the domain runs on the first request, by the names in
    `app.core.middleware.SEEDERS`. A domain seeds only the tables it owns."""
    extra: dict = field(default_factory=dict)
    """Extra keyword arguments for `create_app`."""

    @property
    def service_name(self) -> str:
        """The name this domain's function reports to logs and traces."""
        return SERVICE_NAME_TEMPLATE.format(domain=self.name)

    @property
    def mount_path(self) -> str:
        """Where root A mounts this domain's application."""
        return self.router_prefix or "/"


def _content_routers() -> "list[APIRouter]":
    """Import and return the content domain's routers."""
    from ..domains.content.router import router

    return [router]


def _resume_routers() -> "list[APIRouter]":
    """Import and return the resume domain's routers."""
    from ..domains.resume.router import router

    return [router]


def _identity_routers() -> "list[APIRouter]":
    """Import and return the identity domain's routers."""
    from ..domains.identity.router import router

    return [router]


def _public_routers() -> "list[APIRouter]":
    """Import and return the public domain's routers."""
    from ..domains.public.router import router

    return [router]


DOMAINS: dict[str, Domain] = {
    "content": Domain(
        name="content",
        title="WebbPulse Portfolio content",
        load_routers=_content_routers,
        requires_secrets=("SECRET_KEY",),
        seeds=("site_content",),
    ),
    "resume": Domain(
        name="resume",
        title="WebbPulse Portfolio resume",
        load_routers=_resume_routers,
        requires_secrets=("SECRET_KEY",),
    ),
    "identity": Domain(
        name="identity",
        title="WebbPulse Portfolio identity",
        load_routers=_identity_routers,
        router_prefix=f"{API_PREFIX}/admin",
        router_tags=("admin",),
        requires_secrets=(
            "SECRET_KEY",
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD",
            "ADMIN_EMAIL",
        ),
        seeds=("admin",),
    ),
    "public": Domain(
        name="public",
        title="WebbPulse Portfolio public",
        load_routers=_public_routers,
        router_prefix="",
    ),
}

DOMAIN_NAMES = tuple(DOMAINS)


ENFORCED_ENVIRONMENTS = ("staging", "production")
"""Environments where a missing secret is a startup failure rather than a warning.
Elsewhere a checkout with no AWS has to stay runnable."""


def check_required_secrets(
    domains: "Iterable[Domain]", *, settings: Settings | None = None
) -> None:
    """Fail fast on a missing secret, once at startup, per the domains served.

    Resolution stays lazy, so a root serving no domain that names a secret makes
    no Secrets Manager call. Outside a deployed environment this warns instead.
    """
    wanted = sorted({name for domain in domains for name in domain.requires_secrets})
    if not wanted:
        return
    resolved = settings if settings is not None else get_settings()
    if resolved.environment in ENFORCED_ENVIRONMENTS:
        resolved.require_secrets(*wanted)
        return
    missing = [name for name in wanted if getattr(resolved, name) is None]
    if missing:
        warnings.warn(
            f"Missing secret(s): {', '.join(missing)}. Set them as environment "
            "variables or as keys of the APP_SECRETS_ARN secret. Tokens signed "
            "with an empty key are insecure.",
            UserWarning,
            stacklevel=2,
        )


def build_domain_app(
    domain: Domain | str, *, settings: Settings | None = None
) -> "FastAPI":
    """Build one domain's application: root B's whole job, and root A's unit.

    Both roots go through here, so the middleware stack is identical locally, in
    the suite and in each deployed function.
    """
    from ..core.middleware import DomainHeaderMiddleware, TrailingSlashMiddleware

    if isinstance(domain, str):
        domain = DOMAINS[domain]
    resolved = settings if settings is not None else get_settings()

    app = create_app(
        title=domain.title,
        version=VERSION,
        service_name=domain.service_name,
        settings=resolved,
        include_health=domain.name != "public",
        redirect_slashes=False,
        **ERROR_ENVELOPE_OPTIONS,
        **domain.extra,
    )

    for router in domain.load_routers():
        app.include_router(
            router, prefix=domain.router_prefix, tags=list(domain.router_tags)
        )

    if domain.name == "identity" and resolved.IDENTITY_ISSUER:
        from .identity import build_router

        app.include_router(build_router(resolved))

    if domain.seeds:
        from ..core.middleware import SeedMiddleware

        app.add_middleware(SeedMiddleware, seeds=domain.seeds)
    app.add_middleware(TrailingSlashMiddleware, router=app.router)
    app.add_middleware(DomainHeaderMiddleware, domain=domain.name)
    return app
