"""Login throttling, keyed on the source IP API Gateway actually observed.

The counting is `webbpulse.ratelimit.RateLimiter`, anchored on the first failure
and writing the `failures` attribute this deployment's rows already carry, over
the same `<prefix>-rate-limits` table. The key never comes from
`X-Forwarded-For`, which the caller controls.
"""

import json
import time
from typing import Any, Optional

from fastapi import Request
from webbpulse.http import REQUEST_CONTEXT_HEADER
from webbpulse.ratelimit import TTL_ATTRIBUTE, RateLimiter

from ..config import settings
from ..db.tables import RATE_LIMITS
from .logging import logger

LOGIN_NAMESPACE = "login"
"""The limiter namespace, which is the partition key prefix for its rows."""


def _source_ip_from_context(context: Any) -> str:
    """Pull the source IP out of one API Gateway request context mapping."""
    if not isinstance(context, dict):
        return ""
    http_section = context.get("http")
    if isinstance(http_section, dict):
        source_ip = http_section.get("sourceIp")
        if isinstance(source_ip, str) and source_ip:
            return source_ip
    identity = context.get("identity")
    if isinstance(identity, dict):
        source_ip = identity.get("sourceIp")
        if isinstance(source_ip, str) and source_ip:
            return source_ip
    return ""


def client_ip(request: Request) -> str:
    """The caller's IP, taken from the API Gateway request context.

    The adapter header first, then the Mangum scope, then the socket peer, which
    is reached only locally. `X-Forwarded-For` is never consulted. Kept rather
    than taken from `webbpulse.http.client_ip`, which reads neither the nested
    `requestContext` shape nor the Mangum scope this backend still tolerates.
    """
    raw = request.headers.get(REQUEST_CONTEXT_HEADER)
    if raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(
                "Could not parse the request context header as JSON; ignoring it.",
                extra={"header": REQUEST_CONTEXT_HEADER},
            )
            parsed = None
        source_ip = _source_ip_from_context(parsed)
        if not source_ip and isinstance(parsed, dict):
            source_ip = _source_ip_from_context(parsed.get("requestContext"))
        if source_ip:
            return source_ip

    event = request.scope.get("aws.event")
    if isinstance(event, dict):
        source_ip = _source_ip_from_context(event.get("requestContext"))
        if source_ip:
            return source_ip

    return request.client.host if request.client else "unknown"


def login_limiter() -> RateLimiter:
    """The login failure counter, built per call.

    Per call rather than at import, so a test that moves the table prefix or the
    DynamoDB endpoint underneath the settings gets a limiter pointed at the new
    one rather than a stale boto3 table resource.
    """
    return RateLimiter(
        logical_name=RATE_LIMITS,
        namespace=LOGIN_NAMESPACE,
        anchor="first_request",
        count_attribute="failures",
        prefix=settings.DYNAMODB_TABLE_PREFIX,
        endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
    )


def retry_after(ip: str) -> Optional[int]:
    """Seconds until `ip` may try again, or `None` when it is not locked out.

    A read rather than a count, so asking does not spend an attempt. Every
    failure answers `None`, which is the fail-open path: a limiter that cannot
    read its table must never be what locks a caller out.
    """
    limiter = login_limiter()
    try:
        item = limiter.get({"pk": f"{LOGIN_NAMESPACE}#{ip}"})
    except Exception as error:
        logger.warning(
            "Login rate limit check failed; allowing the request.",
            extra={
                "rate_limit_failed_open": True,
                "rate_limit_namespace": LOGIN_NAMESPACE,
                "rate_limit_operation": "retry_after",
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        return None
    if item is None:
        return None
    expires_at = int(item.get(TTL_ATTRIBUTE, 0))
    remaining = expires_at - int(time.time())
    if remaining <= 0 or int(item.get("failures", 0)) < settings.LOGIN_MAX_FAILURES:
        return None
    return max(remaining, 1)


def record_failure(ip: str) -> Optional[int]:
    """Count one failed attempt, returning the seconds to wait once locked out.

    The cap passed is one below `LOGIN_MAX_FAILURES`, because the shared limiter
    allows the request that reaches the limit and this deployment locks out on it.
    `None` means the caller may try again, which is also what a limiter that
    failed open answers, so a DynamoDB outage never locks anyone out.
    """
    decision = login_limiter().check(
        ip,
        limit=settings.LOGIN_MAX_FAILURES - 1,
        window_seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS,
    )
    if decision.allowed or decision.failed_open:
        return None
    return max(decision.reset_after, 1)


def clear(ip: str) -> None:
    """Forget every recorded failure for `ip`, as a successful login does."""
    login_limiter().clear(ip)
