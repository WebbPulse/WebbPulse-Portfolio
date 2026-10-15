"""The application-wide endpoints: root, health, CORS and trailing slashes."""

import pytest
from fastapi.testclient import TestClient

from app.common.db import client as db_client


@pytest.mark.api
def test_root(client: TestClient):
    """The root endpoint names the API and its version."""
    assert client.get("/").json() == {
        "message": "Portfolio Blog API",
        "version": "1.0.0",
    }


@pytest.mark.api
def test_health(client: TestClient):
    """Health reports healthy when the database answers."""
    assert client.get("/health").json() == {
        "status": "healthy",
        "database": "healthy",
        "version": "1.0.0",
    }


@pytest.mark.api
def test_health_reports_unhealthy_database(client: TestClient):
    """A missing table makes health answer 503 with the database unhealthy."""
    client.get("/")
    db_client.dynamodb_resource().meta.client.delete_table(TableName="webbpulse-test-public-cache")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "healthy",
        "database": "unhealthy",
        "version": "1.0.0",
    }


@pytest.mark.api
@pytest.mark.parametrize("path", ["/api/v1/public/figures", "/api/v1/public/figures/"])
def test_trailing_slash_variants_do_not_redirect(client: TestClient, path, monkeypatch):
    """Both slash forms of a route are served directly rather than redirected."""
    monkeypatch.setattr("app.domains.public.router.current_figures", lambda: [])
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, path


@pytest.mark.api
def test_cors_headers(client: TestClient):
    """A preflight from the dev origin is allowed and permits credentials."""
    response = client.options(
        "/api/v1/public/figures",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.api
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/posts",
        "/api/v1/projects",
        "/api/v1/site-content",
        "/api/v1/admin/users",
        "/api/auth/login",
        "/sitemap.xml",
        "/robots.txt",
    ],
)
def test_retired_routes_are_gone(client: TestClient, path):
    """The content, resume, identity and SEO routes are no longer served."""
    assert client.get(path).status_code == 404
