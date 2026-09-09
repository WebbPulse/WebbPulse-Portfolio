"""The M0 spike's request-context parsing.

The Lambda Web Adapter forwards API Gateway's `requestContext` as a plain JSON
string in `x-amzn-request-context`. The spike originally base64-decoded it, so
every real request failed the decode and `whoami` answered 401 for a token the
gateway had already accepted. These tests pin the plain-JSON reading.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.domains.identity.spike import REQUEST_CONTEXT_HEADER, _request_context, whoami


def _request(header: str | None) -> Request:
    headers = []
    if header is not None:
        headers.append((REQUEST_CONTEXT_HEADER.encode(), header.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/identity/spike/whoami",
            "headers": headers,
            "query_string": b"",
        }
    )


_CONTEXT = {
    "accountId": "123456789012",
    "authorizer": {"jwt": {"claims": {"sub": "spike", "iss": "https://api.example"}}},
    "http": {"method": "GET", "sourceIp": "203.0.113.9"},
}


def test_plain_json_header_is_read_as_the_adapter_sends_it() -> None:
    assert _request_context(_request(json.dumps(_CONTEXT))) == _CONTEXT


def test_missing_header_is_an_empty_context() -> None:
    assert _request_context(_request(None)) == {}


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", "42", ""])
def test_malformed_or_non_object_header_is_an_empty_context(raw: str) -> None:
    assert _request_context(_request(raw)) == {}


def test_whoami_returns_the_claims_the_authorizer_put_in_the_context() -> None:
    body = asyncio.run(whoami(_request(json.dumps(_CONTEXT))))
    assert body["claims"] == {"sub": "spike", "iss": "https://api.example"}
    assert body["authorizer_context_keys"] == ["jwt"]
    assert body["request_context_keys"] == ["accountId", "authorizer", "http"]


def test_whoami_without_claims_is_a_401_rather_than_an_empty_200() -> None:
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(whoami(_request(json.dumps({"http": {"sourceIp": "203.0.113.9"}}))))
    assert excinfo.value.status_code == 401
