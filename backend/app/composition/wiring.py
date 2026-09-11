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

`SeedMiddleware` is deliberately not added to every domain. It writes the
`users` and `site-content` tables on the first request in a process, and
`public` is the domain with read-only DynamoDB and no Secrets Manager access at
all, so wiring it into every domain would make the least-privileged function
attempt two writes it has no IAM for. Only the domains that own those tables
seed them, which is what `seeds` on the descriptor records, and it records
*which* seeds rather than merely whether: `identity` owns `users` and seeds the
admin, `content` owns the singleton and seeds that. Running both in both is what
used to make `content` read the three admin secrets its descriptor says it does
not need.

**Secrets fail at startup, not at the first request that needs one.**
`check_required_secrets` reads `requires_secrets` off the domains a root serves
and calls `settings.require_secrets` for exactly those, once, before the process
serves anything. Resolution itself stays lazy, so the call is what makes a
misconfigured function fail loudly at cold start while `public`, which names no
secret, still makes no Secrets Manager call at all.
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

#: The error envelope options, in one place because both composition roots have
#: to pass them and a root that passed different ones would render a different
#: body for the same failure. `build_domain_app` spreads this, and
#: `app.composition.app` spreads the same dict, so there is a single switch.
#:
#: `error_codes=True` adds a stable `error_code` to every error body:
#: `UNAUTHORIZED`, `NOT_FOUND`, `VALIDATION_ERROR`, `INTERNAL_ERROR` and the
#: rest of the shared package's status table. It is additive. `success`,
#: `status`, `message` and `request_id` keep the values and the order they have
#: always had, so nothing reading the envelope today sees a different answer;
#: what changes is that a caller can branch on a code rather than on the
#: message text. `@webbpulse/api-client` already surfaces it as
#: `getWebbPulseError().errorCode`, and `frontend/src/services/api.ts` already
#: logs it, where it has been `undefined` until now.
#:
#: `validation_details=True` adds `details` to a 422: one
#: `{"field", "message", "type"}` entry per offending field, with the leading
#: `body`/`query` segment dropped so the field reads as the form control's
#: name. The existing `errors` key is untouched, so the older shape still
#: works. The client types `details` as `unknown[] | Record<string, unknown>`,
#: which the list satisfies, and this is the shape a form needs to put a
#: message beside the input that caused it rather than one banner for the
#: whole request.
ERROR_ENVELOPE_OPTIONS: dict[str, bool] = {
    "error_codes": True,
    "validation_details": True,
}

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
    #: `secretsmanager:GetSecretValue` at all. `check_required_secrets` reads
    #: this at startup, so the list is the thing that fails a misconfigured
    #: function rather than a comment about one.
    requires_secrets: tuple[str, ...] = ()
    #: Which seeders the domain runs on the first request, by the names in
    #: `app.core.middleware.SEEDERS`. A domain seeds only the tables it owns:
    #: `identity` owns `users` and so names `admin`, `content` owns the
    #: `site-content` singleton and so names `site_content`, and `public` and
    #: `resume` own neither and name nothing.
    seeds: tuple[str, ...] = ()
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


#: Environments where a missing secret is a startup failure rather than a
#: warning. These are the deployed ones, the two that have an `APP_SECRETS_ARN`
#: and a function whose first request must not be the thing that discovers the
#: secret is unreadable. `local` and `test` stay warnings, which is what keeps a
#: checkout runnable and the suite green with no AWS at all.
ENFORCED_ENVIRONMENTS = ("staging", "production")


def check_required_secrets(
    domains: "Iterable[Domain]", *, settings: Settings | None = None
) -> None:
    """Fail fast on a missing secret, once at startup, per the domains served.

    Resolution stays lazy: nothing here runs at import, and a root that serves
    no domain naming a secret never calls `require_secrets`, so `public` makes
    no Secrets Manager call and needs no `secretsmanager:GetSecretValue` grant.
    What this adds is the moment of truth. Without it a function with the wrong
    ARN starts clean and fails on the first request that happens to verify a
    token, which reads as an intermittent 500 rather than as the
    misconfiguration it is.

    Outside a deployed environment a missing secret is a warning, not a raise.
    A checkout with no AWS has to keep running, and the suite has to stay green
    without a signing key in the environment.
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
        # Spread rather than named, so adding an envelope option is one edit
        # here rather than one per composition root.
        **ERROR_ENVELOPE_OPTIONS,
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

    # The identity standard's M1, on the `identity` domain only and in every
    # environment. `webbpulse.identity.build_identity_router` serves the two
    # `.well-known` documents and its own `/health`, and nothing else: the flows
    # are M2 and later. `app/composition/identity.py` builds the settings and
    # the KMS client.
    #
    # Mounted at the issuer's path, which is load-bearing rather than tidy, and
    # is not the same thing as mounting at the origin.
    #
    # API Gateway builds the discovery URL by appending
    # `/.well-known/openid-configuration` to the configured issuer *including its
    # path*. M0 proved that directly: an issuer of
    # `https://api.staging.webbpulse.com` with no path produced a create-time
    # error quoting `https://api.staging.webbpulse.com/.well-known/openid-
    # configuration`. The standard's issuer is `https://<api host>/api/auth`, so
    # the documents have to answer under `/api/auth`, and `IdentitySettings`
    # agrees: its `discovery_url` and `jwks_url` are `f"{issuer}{PATH}"`, and
    # `jwks_uri` in the served document is built the same way. API Gateway
    # follows that `jwks_uri` literally, so a document advertising a path the
    # router does not serve fails `CreateAuthorizer` at M2.
    #
    # The prefix is therefore derived from the issuer rather than written out, so
    # the mount point and the advertised URLs cannot drift apart. Mounting at the
    # origin instead would serve both documents at paths nothing fetches.
    #
    # SINCE 0.10.0 THE PACKAGE DOES THAT DERIVATION AND THIS MOUNTS NO PREFIX.
    # `build_identity_router` places every route it declares under
    # `identity_prefix(settings)`, the issuer's path. 0.9.0 served the documents
    # at the origin whatever the issuer said, and the workaround here was an
    # `identity_mount_prefix` helper feeding `prefix=`. Passing that prefix now
    # would double every route to `/api/auth/api/auth/...`, and keeping the
    # helper would be a second implementation of a derivation the package owns,
    # which can only drift from it. Both are gone.
    #
    # This is why it does not go through `domain.load_routers`, which mounts
    # everything it loads at this domain's own `/api/v1/admin`.
    #
    # It is deliberately unconditional. The two documents are what this product
    # publishes about itself from M1 on, `terraform/apigateway.tf` carries their
    # route keys unconditionally, and `terraform/identity.tf` creates the signing
    # key they publish in both environments.
    #
    # As of 0.10.0 this also mounts M2's six flow routes, because
    # `composition/identity.py` passes hooks and a credential store and the
    # package mounts the flows conditionally on exactly that pair. They land
    # under the same issuer path: `/api/auth/register` and the rest.
    #
    # The existing `POST /api/v1/admin/login` is untouched. It is a different
    # router at a different prefix signing a different kind of token, and the two
    # run side by side. The cutover that retires the legacy one is M9.
    #
    # Wrapped in a guard on the issuer being configured: `IdentitySettings` requires
    # `IDENTITY_ISSUER` and `IDENTITY_AUDIENCE` and raises without them, and a
    # local checkout or a test that builds the identity application with no
    # identity environment at all must not fail to construct. In a deployed
    # function Terraform always sets both, so the guard is never the reason a
    # document is missing there; a function whose environment is half configured
    # still fails loudly at startup, inside `IdentitySettings`, naming the field.
    if domain.name == "identity" and resolved.IDENTITY_ISSUER:
        from .identity import build_router

        app.include_router(build_router(resolved))

    if domain.seeds:
        from ..core.middleware import SeedMiddleware

        # Only this domain's own seeds. `content` used to run the admin seeder
        # too, which made it write the `users` table and resolve the three admin
        # secrets its descriptor says it does not need.
        app.add_middleware(SeedMiddleware, seeds=domain.seeds)
    app.add_middleware(TrailingSlashMiddleware, router=app.router)
    # Outermost, so the header is on the response whatever the inner stack did
    # with it, error envelopes included. The value is this domain's name, which
    # is what lets a caller tell a flipped route from one still falling through
    # to the monolith on $default.
    app.add_middleware(DomainHeaderMiddleware, domain=domain.name)
    return app
