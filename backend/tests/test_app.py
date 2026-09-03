import pytest
from fastapi.testclient import TestClient

from app.db import client as db_client


@pytest.mark.api
def test_root(client: TestClient):
    assert client.get("/").json() == {
        "message": "Portfolio Blog API",
        "version": "1.0.0",
    }


@pytest.mark.api
def test_health(client: TestClient):
    assert client.get("/health").json() == {
        "status": "healthy",
        "database": "healthy",
        "version": "1.0.0",
    }


@pytest.mark.api
def test_health_reports_unhealthy_database(client: TestClient, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "broken")
    db_client.dynamodb_resource().meta.client.delete_table(
        TableName="webbpulse-test-site-content"
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "unhealthy"


@pytest.mark.api
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/projects",
        "/api/v1/projects/",
        "/api/v1/skills",
        "/api/v1/site-content",
        "/api/v1/posts",
        "/api/v1/posts/categories/",
    ],
)
def test_trailing_slash_variants_do_not_redirect(
    client: TestClient, path, test_site_content
):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200, path


@pytest.mark.api
def test_cors_headers(client: TestClient):
    response = client.options(
        "/api/v1/projects/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.api
def test_rate_limit_endpoints_are_gone(client: TestClient, admin_auth_headers):
    assert (
        client.get(
            "/api/v1/admin/rate-limit/stats", headers=admin_auth_headers
        ).status_code
        == 404
    )
