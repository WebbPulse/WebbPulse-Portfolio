"""Root A: the whole surface in one process.

This is what the `TestClient` suite runs against, and what a developer runs to
serve every route from one process. Root B is `app.entrypoints.<domain>`, one
per deployed function, and both are built from the same domain routers so
neither can drift from the other.

Nothing deploys this module. The four domain functions serve every route in
production, and `docker compose --profile domains up` runs those same four
images locally, which is the closer reproduction. Root A is for the case where
one process serving all 44 routes is more convenient than four containers:

    uvicorn app.composition.app:app --reload

## Why this is not `mount_all`

Section 2 of the plan sketches root A as
`mount_all({"/api/v1/posts": posts_app, ...})`. That sketch does not survive
contact with two facts, both verified rather than assumed, so root A composes
with `include_router` instead and the deviation is written down here rather
than left to be rediscovered.

**Starlette strips a mount path.** `mount_all` is the right shape when each
domain's routers carry no prefix of their own and the mount path supplies it.
Portfolio's routers carry theirs: `content` declares `/posts` and
`/site-content`, `resume` declares five collection prefixes, so one domain is
not one path and there is nothing to mount it at. Mounting a `/api/v1/posts`
app at `/api/v1/posts` yields 404 for every route, because the sub-application
then sees `/api/v1/posts/api/v1/posts/...`.

**A mounted sub-application does not contribute to the parent's OpenAPI
document.** `mount_all`'s parent reports an empty `paths` map, which would take
the monolith's published contract with it. That contract is pinned in
`tests/test_openapi_contract.py` and is the thing PR 3 and PR 4 both promise not
to move.

So the per-domain applications keep `router_prefix="/api/v1"`, which is what
makes each one's routes a literal subset of the monolith's, and root A includes
the same routers directly. `tests/entrypoints/test_route_split.py` asserts the
two agree.

## What this replaced

`app.main` was the monolith's root and is deleted. Its function, integration and
`$default` route were destroyed when section 6 retired the monolith, and the
source went with them in the PR after that.

This module inherited its job as the whole-surface application. It is not a
copy: it differs in exactly the ways the shared package brings, which are the
error envelope and the request id, and it builds from the domain routers rather
than from a second hand-maintained list. The published contract is unchanged
either way, and that is asserted rather than assumed.
`tests/fixtures/route_contract.json` records the 44 routes and 42 operations the
monolith published, `tests/test_openapi_contract.py` holds this application to
them in declaration order, and `tests/entrypoints/test_route_split.py` holds the
four deployed domain applications to the same file and to this application.
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
from .wiring import DOMAINS, check_required_secrets

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


def build_app(settings: Settings | None = None) -> "FastAPI":
    """Every domain's routers on one application.

    The include order is the historical one, taken from `wiring.DOMAINS`, so
    the `paths` map keeps the order the published document has always had.
    """
    resolved = settings if settings is not None else get_settings()

    # Every domain's secrets, because this root serves every domain. Nothing
    # deploys this module, so in practice this is the warning path: a checkout
    # with no signing key gets told once, at startup, rather than on the first
    # request that verifies a token. It raises only if someone runs the whole
    # surface with ENVIRONMENT=staging or production.
    check_required_secrets(DOMAINS.values(), settings=resolved)

    app = create_app(
        title=resolved.APP_NAME,
        version=VERSION,
        service_name="webbpulse-portfolio",
        settings=resolved,
        # `public` declares `GET /health` itself, and it reads DynamoDB to
        # report `database`. Locally that is the useful one, and a duplicate
        # path would mean the first declaration wins silently.
        include_health=False,
        description="Blog API for Portfolio Website",
        redirect_slashes=False,
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
    # Root A is every domain in one process, so no single domain name is true of
    # it. It reports `monolith`, which is also what the deployed monolith
    # reports, and that is the value section 6's verification treats as "this
    # route has not been cut over yet".
    app.add_middleware(DomainHeaderMiddleware, domain=MONOLITH_DOMAIN)
    return app


app = build_app()
