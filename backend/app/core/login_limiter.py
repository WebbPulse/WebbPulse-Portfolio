import time

from botocore.exceptions import ClientError
from fastapi import Request

from ..config import settings
from ..db import client
from ..db.tables import LOGIN_FAIL_PREFIX, META


def now() -> int:
    return int(time.time())


def client_ip(request: Request) -> str:
    event = request.scope.get("aws.event") or {}
    context = event.get("requestContext") or {}
    source_ip = (context.get("http") or {}).get("sourceIp") or (
        context.get("identity") or {}
    ).get("sourceIp")
    if source_ip:
        return source_ip
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoginLimiter:
    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds

    @property
    def table(self):
        return client.table(META)

    @staticmethod
    def key(ip: str) -> dict:
        return {"pk": f"{LOGIN_FAIL_PREFIX}{ip}"}

    def _current(self, ip: str):
        item = self.table.get_item(Key=self.key(ip)).get("Item")
        if not item or int(item.get("ttl", 0)) <= now():
            return None
        return item

    def retry_after(self, ip: str):
        item = self._current(ip)
        if item is None or int(item.get("failures", 0)) < self.max_failures:
            return None
        return max(1, int(item["ttl"]) - now())

    def record_failure(self, ip: str) -> int:
        current = now()
        try:
            response = self.table.update_item(
                Key=self.key(ip),
                UpdateExpression=(
                    "ADD failures :one SET #ttl = if_not_exists(#ttl, :ttl)"
                ),
                ConditionExpression="attribute_not_exists(#ttl) OR #ttl > :now",
                ExpressionAttributeNames={"#ttl": "ttl"},
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
                raise
        self.table.put_item(
            Item={**self.key(ip), "failures": 1, "ttl": current + self.window_seconds}
        )
        return 1

    def clear(self, ip: str) -> None:
        self.table.delete_item(Key=self.key(ip))


login_limiter = LoginLimiter(
    settings.LOGIN_MAX_FAILURES, settings.LOGIN_FAILURE_WINDOW_SECONDS
)
