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
}
"""Settings that let the app factories build without AWS.

Building the document reads no table and signs no token, so these only have to satisfy
`Settings` validation. `ENVIRONMENT` stays outside `ENFORCED_ENVIRONMENTS` so a missing
secret warns instead of refusing, and `APP_SECRETS_ARN` is cleared so no field resolves
through Secrets Manager.
"""

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

    The four functions each serve their own routers and share one origin, so the
    deployed surface is the union rather than any single document. Built per domain
    through `build_domain_app`, the same factory each entrypoint calls.
    """
    for name, value in DOCUMENT_ENVIRONMENT.items():
        os.environ.setdefault(name, value)
    os.environ.pop("APP_SECRETS_ARN", None)

    from app.composition.wiring import DOMAIN_NAMES, build_domain_app

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


def _delete_created(api: Any, created: Sequence[Any]) -> list[str]:
    """Delete everything this run appended, posts before the categories they reference.

    A category the content domain still has a post against refuses to delete, so the
    order here is the dependency order rather than the order things were created.
    """
    order = {CREATED_POST: 0, CREATED_CATEGORY: 1, CREATED_CERTIFICATION: 2}
    paths = {
        CREATED_POST: "/api/v1/posts/admin/{id}",
        CREATED_CATEGORY: "/api/v1/posts/categories/{id}",
        CREATED_CERTIFICATION: "/api/v1/certifications/{id}",
    }
    handles = [item for item in created if isinstance(item, tuple) and len(item) == 2]
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


pytest_plugins = ["webbpulse.e2e"]
