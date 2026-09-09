"""Login throttling, keyed on the source IP API Gateway actually observed.

Two things changed here for the per-domain split, and both are behavioural
rather than cosmetic.

**Where the client IP comes from.** The previous implementation read
`request.scope["aws.event"]`, which is a Mangum artifact. The Lambda Web Adapter
does not populate it, so under the adapter that lookup misses and the old code
fell through to the leftmost `X-Forwarded-For` hop, which the caller controls.
A limiter keyed on a caller controlled value is worse than no limiter, because
anyone can mint a fresh identity per request while the endpoint looks protected.
`client_ip` below reads the `x-amzn-request-context` header the adapter forwards.
It still falls back to the Mangum scope, which is now unreachable in production:
the monolith is deleted and all four functions are adapter images. The fallback
is one dictionary lookup, so it stays rather than being removed in the same
change that removed the runtime it was written for. It never reads
`X-Forwarded-For`.

**Where the items live.** The `LOGIN_FAIL#` items used to be written into the
`meta` table, which also holds the id allocator's counters and uniqueness items
that every writing domain touches. They move to `<prefix>-rate-limits`, matching
`webbpulse.ratelimit`, so the `identity` domain is the only one that needs write
access to them.

That table does not exist yet; PR 9 creates it. Every DynamoDB call here is
therefore wrapped so a missing table, or any other boto3 failure, fails open:
the failure is logged at WARNING with `rate_limit_failed_open=True` and the
request is allowed. A rate limiter is a protective control, not an authorisation
control, so refusing every login because DynamoDB is unavailable turns a
dependency blip into a full outage, which is the worse failure. The WARNING is
the compensating control and is what an alarm should watch.

PR 4 replaces `client_ip` with `webbpulse.http.client_ip` and this limiter with
`webbpulse.ratelimit.RateLimiter`. The logic is deliberately kept equivalent so
that swap is a deletion rather than a rewrite.
"""

import json
import time

from botocore.exceptions import ClientError
from fastapi import Request

from ..config import settings
from ..db import client
from ..db.tables import RATE_LIMIT_TTL_ATTRIBUTE, RATE_LIMITS
from .logging import logger

# The header the Lambda Web Adapter injects, carrying the API Gateway request
# context as a plain JSON string. It is not base64 encoded, so this is a
# straight parse. Matches `webbpulse.http.REQUEST_CONTEXT_HEADER`.
REQUEST_CONTEXT_HEADER = "x-amzn-request-context"

LOGIN_FAIL_PREFIX = "LOGIN_FAIL#"


def now() -> int:
    return int(time.time())


def _source_ip_from_context(context) -> str:
    """Pull the source IP out of one API Gateway request context mapping."""
    if not isinstance(context, dict):
        return ""
    # Payload format 2.0, which is what every HTTP API uses. The adapter's own
    # README example shows `identity.sourceIp`, but that is the 1.0 REST shape
    # and reads as undefined on a 2.0 payload.
    http_section = context.get("http")
    if isinstance(http_section, dict):
        source_ip = http_section.get("sourceIp")
        if isinstance(source_ip, str) and source_ip:
            return source_ip
    # Payload format 1.0, REST APIs.
    identity = context.get("identity")
    if isinstance(identity, dict):
        source_ip = identity.get("sourceIp")
        if isinstance(source_ip, str) and source_ip:
            return source_ip
    return ""


def client_ip(request: Request) -> str:
    """The caller's IP, taken from the API Gateway request context.

    Three sources are tried in order: the `x-amzn-request-context` header the Web
    Adapter forwards, the `aws.event` scope key Mangum populates, and finally the
    real peer address of the socket. The last one is only ever reached in local
    development and in tests, because in production one of the first two is
    always present.

    `X-Forwarded-For` is never consulted. Behind API Gateway its leftmost hop is
    whatever the client sent.
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
        # The adapter forwards the `requestContext` object itself, so the source
        # IP sits at the top level. A caller that hands over the whole event is
        # tolerated too, which keeps the header and scope paths interchangeable.
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

    The window is anchored on the first failure rather than on the clock, which
    is what the previous implementation did and what the existing tests pin, so
    the lockout behaviour a caller sees is unchanged. `webbpulse.ratelimit`
    anchors on the clock instead; that difference is confined to when a window
    starts, not to what is counted or to how the table is shaped.
    """

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds

    @property
    def table(self):
        return client.table(RATE_LIMITS)

    @staticmethod
    def key(ip: str) -> dict:
        return {"pk": f"{LOGIN_FAIL_PREFIX}{ip}"}

    @staticmethod
    def _failed_open(operation: str, error: Exception) -> None:
        """Record a limiter failure that let a request through.

        Deliberately broad at the call sites. botocore raises `ClientError`,
        `EndpointConnectionError`, `NoCredentialsError` and `ReadTimeoutError`
        from unrelated base classes, and the right response to all of them is
        the same: allow the request and make the failure visible.
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
        # The window that was in the item has passed, so this failure starts a
        # new one. An unconditional put is correct here precisely because the
        # old window is spent.
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
        try:
            self.table.delete_item(Key=self.key(ip))
        except Exception as error:
            self._failed_open("clear", error)


login_limiter = LoginLimiter(
    settings.LOGIN_MAX_FAILURES, settings.LOGIN_FAILURE_WINDOW_SECONDS
)
