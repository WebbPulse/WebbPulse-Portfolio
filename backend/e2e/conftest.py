"""Fixtures the `webbpulse.e2e` plugin cannot know: this product's OpenAPI document,
the headers its web client sends, and how to delete what a run created.

The document is built from the same app factories the four deployed functions use, so
it describes exactly the commit under test rather than a checked-in snapshot.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from webbpulse.e2e import (
    Click,
    ExpectText,
    ExpectVisible,
    Fill,
    Goto,
    Journey,
    LoginForm,
    Record,
    RouteSpec,
)

from e2e.resources import CREATED_CATEGORY, CREATED_CERTIFICATION, CREATED_POST

DOCUMENT_ENVIRONMENT = {
    "TESTING": "1",
    "AWS_DEFAULT_REGION": "us-west-2",
    "SECRET_KEY": "e2e-document-only",
    "ADMIN_USERNAME": "e2e-document-only",
    "ADMIN_PASSWORD": "e2e-document-only",
    "ADMIN_EMAIL": "e2e-document-only@webbpulse.com",
    "DYNAMODB_TABLE_PREFIX": "webbpulse-e2e-document",
    "ENVIRONMENT": "test",
    "LOG_LEVEL": "WARNING",
    "IDENTITY_EPHEMERAL_USERS_ENABLED": "true",
}
"""Settings that let the app factories build without AWS.

Building the document reads no table and signs no token, so these only have to satisfy
`Settings` validation. `ENVIRONMENT` stays outside `ENFORCED_ENVIRONMENTS` so a missing
secret warns instead of refusing, and `APP_SECRETS_ARN` is cleared so no field resolves
through Secrets Manager. `IDENTITY_EPHEMERAL_USERS_ENABLED` matches what staging deploys,
so the document is built against the same route set the environment under test mounts.
"""

SCHEMA_ONLY_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})
"""Paths FastAPI adds for its own documentation, which the gateway does not route."""

DOCUMENT_UNSET = ("IDENTITY_ISSUER",)
"""Settings cleared before the document is built, whatever the ambient environment holds.

The identity package annotates nineteen of its route handlers `-> JSONResponse` under
`from __future__ import annotations` while importing that name only under `TYPE_CHECKING`,
so FastAPI cannot resolve the forward reference and tries to build a response model from
it, which raises `PydanticUserError`. `identity_prefix` derives the mount path from the
issuer, so clearing the issuer mounts no identity routes and the document builds. On a
local stack the backend process is given an issuer, and the reusable workflow exports the
whole backend environment job wide, so pytest inherits it and the document would otherwise
fail to build here but not in a deployed run.

Nothing is lost: the identity surface is the shared package's own contract, covered by its
tests rather than by this product's coverage assertions, and the routes the product owns
are unaffected.
"""


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

    The four functions each serve their own routers and share one origin, so the
    deployed surface is the union rather than any single document. Built per domain
    through `build_domain_app`, the same factory each entrypoint calls.
    """
    for name, value in DOCUMENT_ENVIRONMENT.items():
        os.environ.setdefault(name, value)
    os.environ.pop("APP_SECRETS_ARN", None)
    for name in DOCUMENT_UNSET:
        os.environ.pop(name, None)

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


def _delete(api: Any, path: str) -> str | None:
    """Delete one resource, reporting anything but success or an already absent row."""
    response = api.delete(path)
    if response.status_code in (200, 204, 404):
        return None
    return f"DELETE {path} answered {response.status_code}"


def _sweep_stale(api: Any, prefix: str) -> list[str]:
    """Delete this product's `e2e-` resources left behind by a run that died.

    Only rows whose name carries the prefix are touched, so a sweep can never reach a
    real certification or category. The listing endpoints return everything the e2e user
    can see, which is the whole collection, so age is judged from `created_at`.
    """
    import datetime as dt

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    leftovers: list[str | None] = []

    def stale(row: Mapping[str, Any], name_key: str) -> bool:
        """Whether a row carries the e2e prefix and is older than the cutoff."""
        if not str(row.get(name_key, "")).startswith(prefix):
            return False
        created = str(row.get("created_at", ""))
        if not created:
            return True
        try:
            return dt.datetime.fromisoformat(created.replace("Z", "+00:00")) < cutoff
        except ValueError:
            return True

    certifications = api.get("/api/v1/certifications")
    if certifications.status_code == 200:
        for row in certifications.json():
            if stale(row, "name"):
                leftovers.append(_delete(api, f"/api/v1/certifications/{row['id']}"))

    posts = api.get("/api/v1/posts/admin")
    if posts.status_code == 200:
        body = posts.json()
        for row in body if isinstance(body, list) else body.get("items", []):
            if stale(row, "title"):
                leftovers.append(_delete(api, f"/api/v1/posts/admin/{row['id']}"))

    categories = api.get("/api/v1/posts/categories")
    if categories.status_code == 200:
        for row in categories.json():
            if stale(row, "name"):
                leftovers.append(_delete(api, f"/api/v1/posts/categories/{row['id']}"))

    return [item for item in leftovers if item]


def _resolve_named(api: Any, name: str) -> list[tuple[str, Any]]:
    """Every resource whose name or slug is `name`, as the handles `_delete_created` takes.

    A browser journey records the name it typed, because the id the API assigned is never
    shown to the page. Resolving it here keeps that asymmetry inside the cleanup hook
    rather than asking a journey to know an id it cannot see.
    """
    handles: list[tuple[str, Any]] = []

    categories = api.get("/api/v1/posts/categories")
    if categories.status_code == 200:
        for row in categories.json():
            if name in (row.get("name"), row.get("slug")):
                handles.append((CREATED_CATEGORY, row["id"]))

    certifications = api.get("/api/v1/certifications")
    if certifications.status_code == 200:
        for row in certifications.json():
            if row.get("name") == name:
                handles.append((CREATED_CERTIFICATION, row["id"]))

    return handles


def _delete_created(api: Any, created: Sequence[Any]) -> list[str]:
    """Delete everything this run appended, posts before the categories they reference.

    A category the content domain still has a post against refuses to delete, so the
    order here is the dependency order rather than the order things were created. A
    handle recorded as a bare string is a name a browser journey typed, so it is resolved
    to its id first.
    """
    order = {CREATED_POST: 0, CREATED_CATEGORY: 1, CREATED_CERTIFICATION: 2}
    paths = {
        CREATED_POST: "/api/v1/posts/admin/{id}",
        CREATED_CATEGORY: "/api/v1/posts/categories/{id}",
        CREATED_CERTIFICATION: "/api/v1/certifications/{id}",
    }
    handles = [item for item in created if isinstance(item, tuple) and len(item) == 2]
    for item in created:
        if isinstance(item, str) and item:
            handles.extend(_resolve_named(api, item))

    leftovers: list[str | None] = []
    for kind, identifier in sorted(handles, key=lambda item: order.get(item[0], 99)):
        if kind in paths:
            leftovers.append(_delete(api, paths[kind].format(id=identifier)))
    return [item for item in leftovers if item]


def pytest_e2e_cleanup(env: Any, phase: str, created: Sequence[Any]) -> Any:
    """Sweep stale e2e resources at the start of the session and this run's at the end.

    Builds its own client rather than taking the `api` fixture, because the hook is
    called outside a test and a fixture is not available to it. A failure to reach the
    API is returned as a description rather than raised, so a cleanup problem is a
    warning and never the reason a green suite reports red.
    """
    from webbpulse.e2e import E2E_PREFIX, E2EEnvironment
    from webbpulse.e2e.client import E2EClient
    from webbpulse.e2e.identity import login

    if not isinstance(env, E2EEnvironment):
        return None

    gate: dict[str, str] = {}
    if env.gate_ssm_parameter:
        try:
            import boto3
            from webbpulse.e2e import GATE_HEADER

            parameter = boto3.client("ssm", region_name=env.aws_region).get_parameter(
                Name=env.gate_ssm_parameter, WithDecryption=True
            )
            gate = {GATE_HEADER: str(parameter["Parameter"]["Value"])}
        except Exception as error:
            return f"could not read the gate parameter for cleanup: {type(error).__name__}"

    client = E2EClient(base_url=env.api_base_url, gate_headers=gate)
    try:
        api = login(client, env.user_email, env.user_password).client
        if phase == "start":
            return _sweep_stale(api, E2E_PREFIX)
        return _delete_created(api, created)
    except Exception as error:
        return f"cleanup at the {phase} of the session could not run: {type(error).__name__}: {error}"
    finally:
        client.close()


def pytest_e2e_login_form(env: Any) -> LoginForm:
    """Where the admin signs in, and which elements prove the session changed.

    The panel has no separate login route: `/admin` renders the sign-in form while
    anonymous and the panel itself once a token is held, so the login path and the
    protected path are the same one. That makes `protected_redirect` `/admin` as well,
    which is what the anonymous guard case asserts against.

    The four locators are the plugin's own defaults, since the form now carries the
    convention's `data-testid` attributes rather than restating them here.
    """
    return LoginForm(path="/admin", protected_redirect="/admin", guest_redirect="/admin")


def pytest_e2e_routes(env: Any) -> list[RouteSpec]:
    """Every route `App.tsx` declares, and who is allowed to see it.

    `/admin` is the only protected route, and it is protected in place rather than by a
    redirect. Everything else is public: this is a portfolio site, and the identity
    pages are reachable from an emailed link that carries no session, so none of them is
    guest-only. The catch-all is declared too, because a router with no catch-all answers
    200 with an empty root and no server side probe can see it.

    Each `root_locator` names the page's own marker rather than the shared `main`, so a
    route that renders a different page than the one asked for fails here instead of
    passing on whatever the router happened to mount.
    """
    return [
        RouteSpec(path="/", access="public", root_locator="[data-testid=page-home]"),
        RouteSpec(path="/blog", access="public", root_locator="[data-testid=page-blog-list]"),
        RouteSpec(path="/privacy", access="public", root_locator="[data-testid=page-privacy]"),
        RouteSpec(
            path="/verify-email",
            access="public",
            root_locator="[data-testid=page-verify-email]",
        ),
        RouteSpec(
            path="/reset-password",
            access="public",
            root_locator="[data-testid=page-reset-password]",
        ),
        RouteSpec(
            path="/admin",
            access="protected",
            root_locator="[data-testid=signed-in]",
        ),
        RouteSpec(
            path="/does-not-exist",
            access="public",
            root_locator="[data-testid=page-not-found]",
            name="public:catch-all",
        ),
    ]


def pytest_e2e_journeys(env: Any) -> list[Journey]:
    """Short flows through the real UI, one anonymous and one that writes.

    The visitor journey is the one a reader takes: the public blog index has to paint its
    own list rather than the shell alone, which is the failure a 200 hides.

    The admin journey creates a blog category through the panel, which is the shortest
    write the UI offers that needs no other row to reference. The `Record` carries a bare
    string rather than the `(kind, id)` tuple the API flows record, because the plugin
    expands `{run_id}` only in a string and the browser never learns the new row's id.
    `_delete_created` resolves such a string back to an id by name before deleting it.
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
        Journey(
            name="an admin creates a blog category",
            steps=[
                Goto("/admin"),
                ExpectVisible("[data-testid=signed-in]"),
                Click("[data-testid=tab-categories]"),
                Click("[data-testid=category-add]"),
                Fill("[data-testid=category-name]", "e2e-{run_id}-category"),
                Fill("[data-testid=category-slug]", "e2e-{run_id}-category"),
                Record("e2e-{run_id}-category"),
                Click("[data-testid=category-save]"),
                ExpectText("[data-testid=category-list]", "e2e-{run_id}-category"),
            ],
            mutates=True,
        ),
    ]


pytest_plugins = ["webbpulse.e2e"]
