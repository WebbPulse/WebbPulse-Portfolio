"""Read the application's secrets from AWS Secrets Manager, lazily and cached.

`APP_SECRETS_ARN` names one JSON secret per service per environment, flattened
here to the string map `Settings` assigns from. No value is ever logged.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from webbpulse.config import load_json_secret, reset_secret_cache

logger = logging.getLogger(__name__)

_cache: Optional[dict[str, str]] = None
"""The flattened string map, cached separately from the shared loader's parsed
object, so a repeated read does neither the fetch nor the flatten."""


def load_app_secrets(secret_arn: str, client: Any = None) -> dict[str, str]:
    """Return the secret's JSON object as a flat map of strings.

    Anything that stops the blob being read raises, so a misconfigured function
    fails at cold start. Non-string values are JSON encoded and nulls dropped.
    """
    global _cache
    if _cache is not None:
        return _cache

    if client is not None:
        payload = _fetch_with(client, secret_arn)
    else:
        try:
            payload = load_json_secret(secret_arn)
        except Exception:
            logger.exception("Failed to read application secrets from %s", secret_arn)
            raise

    values = {
        name: value if isinstance(value, str) else json.dumps(value)
        for name, value in payload.items()
        if value is not None
    }
    logger.info(
        "Loaded %d application secrets from %s: %s",
        len(values),
        secret_arn,
        ", ".join(sorted(values)),
    )
    _cache = values
    return values


def _fetch_with(client: Any, secret_arn: str) -> dict[str, Any]:
    """The shared loader's read and parse, against a caller supplied client.

    Repeats the loader's checks and raises the same `ValueError`, so both paths
    agree on what an unusable secret is.
    """
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception:
        logger.exception("Failed to read application secrets from %s", secret_arn)
        raise

    body = response.get("SecretString")
    if body is None:
        raise ValueError(f"Secret {secret_arn} holds binary data, not a JSON object.")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Secret {secret_arn} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Secret {secret_arn} parsed as {type(payload).__name__}, expected a JSON object.")
    return payload


def reset_cache() -> None:
    """Drop the cached values, here and in the shared loader. For tests.

    Both halves, since clearing only the local map would refill it from the
    shared cache's stale parse.
    """
    global _cache
    _cache = None
    reset_secret_cache()
