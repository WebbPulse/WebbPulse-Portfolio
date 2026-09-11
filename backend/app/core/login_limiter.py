"""Login throttling, keyed on the source IP API Gateway actually observed.

The key never comes from `X-Forwarded-For`, which the caller controls. Every
DynamoDB call fails open and logs, since a limiter outage must not block login.
"""

import json
import time

from botocore.exceptions import ClientError
from fastapi import Request

from ..config import settings
from ..db import client
from ..db.tables import RATE_LIMIT_TTL_ATTRIBUTE, RATE_LIMITS
from .logging import logger

#: The header the Lambda Web Adapter injects, carrying the API Gateway request
#: context as a plain, unencoded JSON string.
REQUEST_CONTEXT_HEADER = "x-amzn-request-context"

LOGIN_FAIL_PREFIX = "LOGIN_FAIL#"


def now() -> int:
    """The current Unix time in whole seconds."""
    return int(time.time())


def _source_ip_from_context(context) -> str:
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
    is reached only locally. `X-Forwarded-For` is never consulted.
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


class LoginLimiter:
    """Fixed window failure counter over the `<prefix>-rate-limits` table.

    The window is anchored on the first failure rather than on the clock.
    """

    def __init__(self, max_failures: int, window_seconds: int):
        """Lock out after `max_failures` within `window_seconds`."""
        self.max_failures = max_failures
        self.window_seconds = window_seconds

    @property
    def table(self):
        """The rate limits table resource, resolved per call."""
        return client.table(RATE_LIMITS)

    @staticmethod
    def key(ip: str) -> dict:
        """The primary key of the failure counter for one IP."""
        return {"pk": f"{LOGIN_FAIL_PREFIX}{ip}"}

    @staticmethod
    def _failed_open(operation: str, error: Exception) -> None:
        """Record a limiter failure that let a request through.

        Caught broadly at the call sites: every botocore failure gets the same
        response, which is to allow the request and make it visible.
        """
        logger.warning(
            "Login rate limit check failed; allowing the request.",
            extra={
                "rate_limit_failed_open": True,
                "rate_limit_operation": operation,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )

    def _current(self, ip: str):
        """The live counter item for `ip`, or `None` when its window has passed."""
        item = self.table.get_item(Key=self.key(ip)).get("Item")
        if not item or int(item.get(RATE_LIMIT_TTL_ATTRIBUTE, 0)) <= now():
            return None
        return item

    def retry_after(self, ip: str):
        """Seconds until `ip` may try again, or None when it is not locked out."""
        try:
            item = self._current(ip)
        except Exception as error:
            self._failed_open("retry_after", error)
            return None
        if item is None or int(item.get("failures", 0)) < self.max_failures:
            return None
        return max(1, int(item[RATE_LIMIT_TTL_ATTRIBUTE]) - now())

    def record_failure(self, ip: str) -> int:
        """Count one failed attempt and return the running total for the window.

        Returns 0 when the counter could not be written, which is below every
        threshold and so allows the request. That is the fail-open path.
        """
        current = now()
        try:
            response = self.table.update_item(
                Key=self.key(ip),
                UpdateExpression=(
                    "ADD failures :one SET #ttl = if_not_exists(#ttl, :ttl)"
                ),
                ConditionExpression="attribute_not_exists(#ttl) OR #ttl > :now",
                ExpressionAttributeNames={"#ttl": RATE_LIMIT_TTL_ATTRIBUTE},
                ExpressionAttributeValues={
                    ":one": 1,
                    ":ttl": current + self.window_seconds,
                    ":now": current,
                },
                ReturnValues="ALL_NEW",
            )
            return int(response["Attributes"]["failures"])
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                self._failed_open("record_failure", error)
                return 0
        except Exception as error:
            self._failed_open("record_failure", error)
            return 0
        try:
            self.table.put_item(
                Item={
                    **self.key(ip),
                    "failures": 1,
                    RATE_LIMIT_TTL_ATTRIBUTE: current + self.window_seconds,
                }
            )
        except Exception as error:
            self._failed_open("record_failure", error)
            return 0
        return 1

    def clear(self, ip: str) -> None:
        """Forget every recorded failure for `ip`, as a successful login does."""
        try:
            self.table.delete_item(Key=self.key(ip))
        except Exception as error:
            self._failed_open("clear", error)


login_limiter = LoginLimiter(
    settings.LOGIN_MAX_FAILURES, settings.LOGIN_FAILURE_WINDOW_SECONDS
)
