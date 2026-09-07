"""Root A: the whole surface in one process.

This is what local development, `docker-compose`, and the existing `TestClient`
suite run against. Root B is `app.entrypoints.<domain>`, one per deployed
function, and both are built from the same domain routers so neither can drift
from the other.

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

## Why `app.main` is still the deployed monolith

`app.main` is untouched by this PR and stays the app the monolith Lambda serves
until the last cut in section 6 retires it. Its OpenAPI document is byte
identical to what it was, which is the point. This module is the root the split
is built on, and it differs from `app.main` in exactly the ways the shared
package brings: the error envelope, the request id, and a liveness-only
`/health` beside the database-reading one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from webbpulse.http import create_app

from ..core.middleware import SeedMiddleware, TrailingSlashMiddleware
from ..version import VERSION
from .settings import Settings, get_settings
from .wiring import DOMAINS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


def build_app(settings: Settings | None = None) -> "FastAPI":
    """Every domain's routers on one application.

    The include order is the historical one, taken from `wiring.DOMAINS`, so
    the `paths` map keeps the order the published document has always had.
    """
    resolved = settings if settings is not None else get_settings()

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
    return app


app = build_app()
