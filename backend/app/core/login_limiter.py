"""Login throttling, keyed on the source IP API Gateway actually observed.

The counting is `webbpulse.ratelimit.RateLimiter`, anchored on the first failure
and writing the `failures` attribute this deployment's rows already carry, over
the same `<prefix>-rate-limits` table. The key never comes from
`X-Forwarded-For`, which the caller controls.

Whether the limiter counts at all follows `settings.rate_limiting_enabled`, the
shared package's convention, so staging is never rate limited and every other
environment keeps its lockout.
"""

import json
import time
from typing import Any, Callable, Optional

from fastapi import Request
from webbpulse.http import REQUEST_CONTEXT_HEADER
from webbpulse.ratelimit import TTL_ATTRIBUTE, RateLimiter

from ..config import get_settings
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


def _rate_limiting_enabled() -> bool:
    """The shared convention's answer for this process, read fresh each call.

    Through `get_settings` rather than an import-time snapshot, so a test that
    moves the environment and drops the cache gets the new answer.
    """
    return get_settings().rate_limiting_enabled


class LoginLimiter:
    """The per-IP login failure counter, and the switch that turns it off.

    `enabled` is asked before every read and every write, so an environment the
    convention leaves unlimited never reaches DynamoDB at all and a wrong
    password there is simply a 401.
    """

    def __init__(self, enabled: Callable[[], bool] = _rate_limiting_enabled) -> None:
        """Hold the switch; the limiter itself is built per call, not here."""
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether this process counts login failures at all."""
        return self._enabled()

    def limiter(self) -> RateLimiter:
        """The shared package limiter, built per call.

        Per call rather than at import, so a test that moves the table prefix or
        the DynamoDB endpoint underneath the settings gets a limiter pointed at
        the new one rather than a stale boto3 table resource.
        """
        settings = get_settings()
        return RateLimiter(
            logical_name=RATE_LIMITS,
            namespace=LOGIN_NAMESPACE,
            anchor="first_request",
            count_attribute="failures",
            prefix=settings.DYNAMODB_TABLE_PREFIX,
            endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
        )

    def retry_after(self, ip: str) -> Optional[int]:
        """Seconds until `ip` may try again, or `None` when it is not locked out.

        A read rather than a count, so asking does not spend an attempt. Every
        failure answers `None`, which is the fail-open path: a limiter that cannot
        read its table must never be what locks a caller out. Disabled answers
        `None` without a read.
        """
        if not self.enabled:
            return None
        settings = get_settings()
        limiter = self.limiter()
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

    def record_failure(self, ip: str) -> Optional[int]:
        """Count one failed attempt, returning the seconds to wait once locked out.

        The cap passed is one below `LOGIN_MAX_FAILURES`, because the shared limiter
        allows the request that reaches the limit and this deployment locks out on it.
        `None` means the caller may try again, which is also what a limiter that
        failed open answers, so a DynamoDB outage never locks anyone out. Disabled
        records nothing and answers `None`.
        """
        if not self.enabled:
            return None
        settings = get_settings()
        decision = self.limiter().check(
            ip,
            limit=settings.LOGIN_MAX_FAILURES - 1,
            window_seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS,
        )
        if decision.allowed or decision.failed_open:
            return None
        return max(decision.reset_after, 1)

    def clear(self, ip: str) -> None:
        """Forget every recorded failure for `ip`, as a successful login does.

        Disabled writes nothing, because nothing was ever counted.
        """
        if not self.enabled:
            return
        self.limiter().clear(ip)


_LIMITER = LoginLimiter()
"""The process-wide login limiter, which the module functions delegate to."""


def login_limiter() -> RateLimiter:
    """The shared package limiter behind the process-wide `LoginLimiter`."""
    return _LIMITER.limiter()


def retry_after(ip: str) -> Optional[int]:
    """Seconds until `ip` may try again, or `None` when it is not locked out."""
    return _LIMITER.retry_after(ip)


def record_failure(ip: str) -> Optional[int]:
    """Count one failed attempt, returning the seconds to wait once locked out."""
    return _LIMITER.record_failure(ip)


def clear(ip: str) -> None:
    """Forget every recorded failure for `ip`, as a successful login does."""
    _LIMITER.clear(ip)
