"""The four domains, and how a per-domain application is built from one.

This is the single description of what each domain is: its name, the service
name its function reports, the routers it owns, and whether it mounts under
`/api/v1` or at the root. Root A (`app.composition.app`) walks the whole map;
root B (`app.entrypoints.<domain>`) picks one entry out of it. Neither of them
holds a second copy of the list, which is what stops the mounted application and
the deployed function drifting apart.

**`build_domain_app` is where every per-domain application comes from**, and the
three arguments it always passes are the ones the plan calls out:

- `router_prefix` is `/api/v1` for the three API domains and empty for `public`,
  whose four routes are unprefixed.
- `redirect_slashes=False` goes through `**fastapi_kwargs`, because `create_app`
  has no parameter for it. The monolith has always set it and the frontend
  depends on it: `getProjects(true)` emits the malformed
  `/projects?featured_only=true/`, which `TrailingSlashMiddleware` absorbs. With
  redirects on, that URL 307s to a path that does not exist.
- `TrailingSlashMiddleware` is added after `create_app` returns, so it sits
  inside the middleware `create_app` installed, exactly where it sits in the
  monolith.

`SeedMiddleware` is deliberately not here. It writes the `users` and
`site-content` tables on the first request in a process, and `public` is the
domain with read-only DynamoDB and no Secrets Manager access at all, so wiring
it into every domain would make the least-privileged function attempt two writes
it has no IAM for. Only the domains that own those tables seed them, which is
what `seeds` on the descriptor records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from webbpulse.http import create_app

from ..version import VERSION
from .settings import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import APIRouter, FastAPI

API_PREFIX = "/api/v1"

#: Service name pattern. Terraform sets `SERVICE_NAME` to the same string, and it
#: becomes the OpenTelemetry `service.name` and the `service` field on every log
#: line, so the two have to agree.
SERVICE_NAME_TEMPLATE = "webbpulse-portfolio-{domain}"


@dataclass(frozen=True)
class Domain:
    """One deployable domain."""

    name: str
    title: str
    #: Called lazily so importing this module imports no domain package. An
    #: entrypoint that only needs `public` must not pay for importing `content`.
    load_routers: Callable[[], "list[APIRouter]"]
    #: Where the domain's routers mount. `public` is unprefixed, and `identity`
    #: adds `/admin` because PR 3 left that prefix on the composition root
    #: rather than inside the domain: `domains/identity/router.py` declares a
    #: bare `POST /login`. Both roots therefore have to supply it, and putting
    #: it on the descriptor is what stops them supplying different values.
    router_prefix: str = API_PREFIX
    #: Tags applied when the routers mount, for the same reason as the prefix.
    router_tags: tuple[str, ...] = ()
    #: Which of the four secret fields the domain cannot serve a request without.
    #: `public` names none, which is what lets its function run with no
    #: `secretsmanager:GetSecretValue` at all.
    requires_secrets: tuple[str, ...] = ()
    #: Whether the domain seeds the tables it owns on the first request.
    seeds: bool = False
    #: Extra keyword arguments for `create_app`.
    extra: dict = field(default_factory=dict)

    @property
    def service_name(self) -> str:
        return SERVICE_NAME_TEMPLATE.format(domain=self.name)

    @property
    def mount_path(self) -> str:
        """Where root A mounts this domain's application."""
        return self.router_prefix or "/"


def _content_routers() -> "list[APIRouter]":
    from ..domains.content.router import router

    return [router]


def _resume_routers() -> "list[APIRouter]":
    from ..domains.resume.router import router

    return [router]


def _identity_routers() -> "list[APIRouter]":
    from ..domains.identity.router import router

    return [router]


def _public_routers() -> "list[APIRouter]":
    from ..domains.public.router import router

    return [router]


DOMAINS: dict[str, Domain] = {
    "content": Domain(
        name="content",
        title="WebbPulse Portfolio content",
        load_routers=_content_routers,
        requires_secrets=("SECRET_KEY",),
        seeds=True,
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
        seeds=True,
    ),
    "public": Domain(
        name="public",
        title="WebbPulse Portfolio public",
        load_routers=_public_routers,
        router_prefix="",
    ),
}

DOMAIN_NAMES = tuple(DOMAINS)


def build_domain_app(
    domain: Domain | str, *, settings: Settings | None = None
) -> "FastAPI":
    """Build one domain's application: root B's whole job, and root A's unit.

    `create_app` adds, in request-traversal order, CORS, the request id
    middleware, the structured error handlers and the liveness-only
    `GET /health`. Because both roots go through here, that stack is identical
    locally, in the test suite, and in each deployed function.

    The domain's own `/health` is not the adapter's. `public` declares a
    `GET /health` that reads DynamoDB to report `database`, and the Web Adapter
    polls `/health` on every cold start, so `create_app`'s I/O-free route must
    win. `include_health` is therefore off for `public` and on for the other
    three, and `public`'s database check keeps the path it has always had by
    being the only `/health` its application declares. Section 6's first cut
    routes `GET /health` to `public`, which is what keeps the existing smoke
    test meaningful.
    """
    # Imported here, not at module scope. `app.core.middleware` imports the two
    # domains it seeds, so importing it at the top would pull `content` and
    # `identity` into every entrypoint and undo the whole point of the split:
    # the `public` image would carry `content`'s modules and pay their import
    # at every cold start.
    from ..core.middleware import DomainHeaderMiddleware, TrailingSlashMiddleware

    if isinstance(domain, str):
        domain = DOMAINS[domain]
    resolved = settings if settings is not None else get_settings()

    app = create_app(
        title=domain.title,
        version=VERSION,
        service_name=domain.service_name,
        settings=resolved,
        # `public` declares its own `/health`, so the shared one would be a
        # duplicate path and the first declaration would win.
        include_health=domain.name != "public",
        redirect_slashes=False,
        **domain.extra,
    )

    # `create_app` takes a single `router_prefix` and no tags, so the routers
    # are included here instead. That keeps the prefix and the tags in one
    # place on the descriptor, which is what makes a domain application's
    # paths, operation ids and tags identical to the monolith's.
    for router in domain.load_routers():
        app.include_router(
            router, prefix=domain.router_prefix, tags=list(domain.router_tags)
        )

    if domain.seeds:
        from ..core.middleware import SeedMiddleware

        app.add_middleware(SeedMiddleware)
    app.add_middleware(TrailingSlashMiddleware, router=app.router)
    # Outermost, so the header is on the response whatever the inner stack did
    # with it, error envelopes included. The value is this domain's name, which
    # is what lets a caller tell a flipped route from one still falling through
    # to the monolith on $default.
    app.add_middleware(DomainHeaderMiddleware, domain=domain.name)
    return app
