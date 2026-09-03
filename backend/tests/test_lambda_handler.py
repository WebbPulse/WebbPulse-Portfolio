import json
from types import SimpleNamespace

import pytest

from app.lambda_handler import handler


def api_gateway_event(method, path, body=None, headers=None, source_ip="203.0.113.7"):
    headers = {"host": "api.example.com", **(headers or {})}
    event = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "abc123",
            "domainName": "api.example.com",
            "domainPrefix": "api",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": source_ip,
                "userAgent": "pytest",
            },
            "requestId": "req-1",
            "routeKey": "$default",
            "stage": "$default",
            "time": "01/Jan/2024:00:00:00 +0000",
            "timeEpoch": 1704067200000,
        },
        "isBase64Encoded": False,
    }
    if body is not None:
        event["body"] = json.dumps(body)
        event["headers"]["content-type"] = "application/json"
    return event


def lambda_context():
    return SimpleNamespace(
        function_name="portfolio-api",
        memory_limit_in_mb=512,
        invoked_function_arn=(
            "arn:aws:lambda:us-west-2:123456789012:function:portfolio-api"
        ),
        aws_request_id="00000000-0000-0000-0000-000000000000",
    )


def invoke(method, path, **kwargs):
    response = handler(api_gateway_event(method, path, **kwargs), lambda_context())
    try:
        body = json.loads(response["body"]) if response.get("body") else None
    except json.JSONDecodeError:
        body = response["body"]
    return response["statusCode"], body, response


@pytest.mark.integration
def test_health_through_handler():
    status, body, _ = invoke("GET", "/health")
    assert status == 200
    assert body == {"status": "healthy", "database": "healthy", "version": "1.0.0"}


@pytest.mark.integration
def test_paths_resolve_with_and_without_trailing_slash(test_project):
    for path in ("/api/v1/projects", "/api/v1/projects/"):
        status, body, response = invoke("GET", path)
        assert status == 200, path
        assert "location" not in {k.lower() for k in response.get("headers", {})}
        assert [item["title"] for item in body] == ["Test Project"]
    status, body, _ = invoke("GET", "/api/v1/projects/1/")
    assert status == 200 and body["id"] == 1


@pytest.mark.integration
def test_unknown_path_is_404():
    status, body, _ = invoke("GET", "/api/v1/nothing")
    assert status == 404


@pytest.mark.integration
def test_login_uses_api_gateway_source_ip(test_admin_user, client):
    from app.config import settings

    for _ in range(settings.LOGIN_MAX_FAILURES):
        status, _, _ = invoke(
            "POST",
            "/api/v1/admin/login",
            body={"username": "adminuser", "password": "wrong"},
            source_ip="198.51.100.9",
        )
    assert status == 429
    other = client.post(
        "/api/v1/admin/login",
        json={"username": "adminuser", "password": "adminpassword123"},
        headers={"X-Forwarded-For": "198.51.100.9"},
    )
    assert other.status_code == 429
    status, body, _ = invoke(
        "POST",
        "/api/v1/admin/login",
        body={"username": "adminuser", "password": "adminpassword123"},
        source_ip="198.51.100.10",
    )
    assert status == 200 and body["token_type"] == "bearer"


@pytest.mark.integration
def test_cors_preflight_through_handler():
    status, _, response = invoke(
        "OPTIONS",
        "/api/v1/projects/",
        headers={
            "origin": "http://localhost:5173",
            "access-control-request-method": "GET",
        },
    )
    assert status == 200
    headers = {k.lower(): v for k, v in response["headers"].items()}
    assert headers["access-control-allow-origin"] == "http://localhost:5173"
