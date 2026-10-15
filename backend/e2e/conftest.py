"""Fixtures the `webbpulse.e2e` plugin cannot know: this product's OpenAPI document,
the headers its web client sends, and which of the plugin's cases it has nothing for.

The document is built from the same app factory the deployed function uses, so it
describes exactly the commit under test rather than a checked-in snapshot.

Portfolio has no sign-in, so every case that signs in, mints a token or writes is
skipped here, whatever the environment, rather than left to fail against routes that
no longer exist.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from webbpulse.e2e import ExpectVisible, Goto, Journey, RouteSpec

DOCUMENT_ENVIRONMENT = {
    "TESTING": "1",
    "AWS_DEFAULT_REGION": "us-west-2",
    "DYNAMODB_TABLE_PREFIX": "webbpulse-e2e-document",
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "WARNING",
}
"""Settings that let the app factory build without AWS. Building the document reads no
table, so these only have to satisfy `Settings` validation."""

NO_SIGN_IN_REASON = "Portfolio has no sign-in, so there is no user to sign in as and nothing to write."
"""Why the plugin's signed-in, minting and writing cases are skipped in every environment."""

SIGN_IN_FIXTURES = frozenset(
    {
        "api",
        "user_session",
        "stepped_up_session",
        "credentials",
        "ephemeral_user",
        "admin_mint_token",
        "minted_subject",
    }
)
"""Plugin fixtures that sign in or mint, so a case asking for one has nothing to run against."""

NO_SIGN_IN_GROUPS = frozenset({"TestIdentity"})
"""Plugin groups that exercise the identity service, which Portfolio no longer runs."""

SCHEMA_ONLY_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})
"""Paths FastAPI adds for its own documentation, which the gateway does not route."""


def _gateway_path(path: str) -> str:
    """The spelling API Gateway routes, which never carries a trailing slash.

    The application declares collection routes with one and tolerates either through
    `TrailingSlashMiddleware`, but that middleware runs only once a request has already
    been routed. `terraform/apigateway.tf` declares the keys unslashed, and the gateway
    neither normalises an inbound slash nor matches a key carrying one, so a slashed
    request falls through to the `{proxy+}` catch-all with no authorizer claims. The
    document has to describe the unslashed spelling or the coverage assertions would be
    made against paths the edge never sees.
    """
    return path if path == "/" else path.rstrip("/")


def _merged_document() -> dict[str, Any]:
    """Every domain's OpenAPI document merged into the one the gateway fronts.

    Each function serves its own routers behind one origin, so the deployed surface is
    the union rather than any single document. Built per domain through
    `build_domain_app`, the same factory each entrypoint calls.
    """
    for name, value in DOCUMENT_ENVIRONMENT.items():
        os.environ.setdefault(name, value)

    from app.common.composition.wiring import DOMAIN_NAMES, build_domain_app

    merged: dict[str, Any] = {}
    info: dict[str, Any] = {}
    for name in DOMAIN_NAMES:
        document = build_domain_app(name).openapi()
        info = info or dict(document.get("info", {}))
        for path, item in document.get("paths", {}).items():
            if path in SCHEMA_ONLY_PATHS:
                continue
            merged.setdefault(_gateway_path(path), {}).update(item)

    return {"openapi": "3.1.0", "info": info, "paths": merged}


def e2e_openapi_document() -> dict[str, Any]:
    """The deployed commit's OpenAPI document, read at collection time.

    A module level function as well as a fixture because the plugin parametrises the
    coverage and reachability cases before any fixture has run.
    """
    return _merged_document()


@pytest.fixture(scope="session")
def openapi_document() -> Mapping[str, Any]:
    """The same document, for the fixtures that take it."""
    return e2e_openapi_document()


@pytest.fixture(scope="session")
def cors_request_headers() -> tuple[str, ...]:
    """The header names `@webbpulse/api-client` sends on a cross origin request.

    `x-retry-attempt` is in the list because the client stamps it on every retry and a
    gateway allow list that omits it rejects exactly the requests a flaky call depends
    on, which is invisible to any probe that never retries.
    """
    return ("authorization", "content-type", "x-request-id", "x-retry-attempt")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip every plugin case that signs in, mints or writes, in every environment."""
    skip = pytest.mark.skip(reason=NO_SIGN_IN_REASON)
    for item in items:
        group = getattr(item.cls, "__name__", "")
        fixtures = set(getattr(item, "fixturenames", ()))
        if group in NO_SIGN_IN_GROUPS or fixtures & SIGN_IN_FIXTURES or item.get_closest_marker("e2e_writes"):
            item.add_marker(skip)


def pytest_e2e_cleanup(env: Any, phase: str, created: Sequence[Any]) -> Any:
    """Nothing to clean up: no case writes, so a run creates nothing."""
    return None


def pytest_e2e_routes(env: Any) -> list[RouteSpec]:
    """Every route `App.tsx` declares, all of them public.

    The site has no sign-in, so no route is protected or guest-only and the plugin's
    browser sign-in cases skip, as no `pytest_e2e_login_form` hook is implemented. The
    catch-all is declared because a router with no catch-all answers 200 with an empty
    root and no server side probe can see it, and `/admin` is declared against the 404
    marker so the removed panel cannot quietly come back.

    Each `root_locator` names the page's own marker rather than the shared `main`, so a
    route that renders a different page than the one asked for fails here instead of
    passing on whatever the router happened to mount.
    """
    return [
        RouteSpec(path="/", access="public", root_locator="[data-testid=page-home]"),
        RouteSpec(path="/blog", access="public", root_locator="[data-testid=page-blog-list]"),
        RouteSpec(path="/privacy", access="public", root_locator="[data-testid=page-privacy]"),
        RouteSpec(
            path="/work/standupless",
            access="public",
            root_locator="[data-testid=page-case-study]",
        ),
        RouteSpec(
            path="/admin",
            access="public",
            root_locator="[data-testid=page-not-found]",
            name="public:removed-admin",
        ),
        RouteSpec(
            path="/does-not-exist",
            access="public",
            root_locator="[data-testid=page-not-found]",
            name="public:catch-all",
        ),
    ]


def pytest_e2e_journeys(env: Any) -> list[Journey]:
    """The one flow a reader takes through the real UI.

    The public blog index has to paint its own list rather than the shell alone, which
    is the failure a 200 hides.
    """
    return [
        Journey(
            name="a visitor reads the blog index",
            signed_in=False,
            steps=[
                Goto("/blog"),
                ExpectVisible("[data-testid=page-blog-list]"),
            ],
        ),
    ]


pytest_plugins = ["webbpulse.e2e"]
