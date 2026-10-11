"""Root A: every domain's routers on one application, in one process.

What the test suite and a local `uvicorn app.common.composition.app:app` run against.
Nothing deploys it; the four domain functions serve every route in production.

It goes through the same `wiring.build` as each function, so both router kinds are
mounted exactly as they are for one domain: the prefixed routers under the domain's
prefix and the routers that declare their own full paths at the root. The identity
package's routes are the second kind, so a root that mounted only the first would
serve no login at all.

In the local environment the gateway's JWT authorizer is stood in for by the shared
`local_authorizer`, since without it a valid token reaches every admin route carrying
no verified claims and each one answers 401.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from webbpulse.composition import Domain, local_authorizer
from webbpulse.http import MONOLITH_DOMAIN

from .settings import Settings, get_settings
from .wiring import DOMAINS, build, check_required_secrets

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


def _build_identity_settings(_settings: Settings):
    """The shared identity settings, read from the `IDENTITY_` environment."""
    from webbpulse.identity import IdentitySettings

    return IdentitySettings()  # pyright: ignore[reportCallIssue]


def _local_authorizer(settings: Settings):
    """A hook standing the gateway's authorizer up in process, on a local stack only."""

    def hook(app: "FastAPI", domains: Sequence[Domain]) -> None:
        """Add `LocalAuthorizerMiddleware` when this is a local stack with an issuer."""
        local_authorizer(app, settings, build_identity_settings=_build_identity_settings)

    return hook


def build_app(settings: Settings | None = None) -> "FastAPI":
    """Every domain's routers on one application.

    The include order is `wiring.DOMAINS`, so the `paths` map keeps the order
    the published document has always had.
    """
    resolved = settings if settings is not None else get_settings()

    check_required_secrets(DOMAINS.values(), settings=resolved)

    return build(
        list(DOMAINS.values()),
        settings=resolved,
        domain_header=MONOLITH_DOMAIN,
        seeds=None,
        before_routing=[_local_authorizer(resolved)],
        title=resolved.APP_NAME,
        service_name="webbpulse-portfolio",
        include_health=False,
        description="Blog API for Portfolio Website",
    )


app = build_app()
