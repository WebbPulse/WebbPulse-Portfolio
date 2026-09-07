"""Read the application's secrets from AWS Secrets Manager at cold start.

One secret per service per environment: APP_SECRETS_ARN names a single
Secrets Manager secret whose string is a JSON object, and its keys are the
settings names the application expects, SECRET_KEY, ADMIN_USERNAME,
ADMIN_PASSWORD and ADMIN_EMAIL. That is the shape the app-secrets Terraform
module's `json` field creates.

The blob is fetched once per execution environment and cached in module scope,
so a warm Lambda invocation makes no Secrets Manager call.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)

_client = None
_cache: Optional[dict[str, str]] = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("secretsmanager")
    return _client


def load_app_secrets(secret_arn: str, client: Any = None) -> dict[str, str]:
    """Return the secret's JSON object as a flat map of strings.

    Anything that stops the blob being read is fatal: a denied read, a missing
    secret, a secret with no version, a body that is not JSON, a JSON document
    that is not an object. All of them mean the function is misconfigured and
    must fail at cold start rather than start up without a signing key. Values
    that are not strings are JSON-encoded so the caller always gets strings;
    null values are dropped, which is how the module represents "absent".
    """
    global _cache
    if _cache is not None:
        return _cache

    try:
        secrets_client = client if client is not None else _get_client()
        response = secrets_client.get_secret_value(SecretId=secret_arn)
    except Exception:
        logger.exception("Failed to read application secrets from %s", secret_arn)
        raise

    body = response.get("SecretString")
    if body is None:
        logger.error("Secret %s holds binary data, not a string", secret_arn)
        raise ValueError(f"Secret {secret_arn} must hold a JSON object as a string")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Secret %s is not valid JSON", secret_arn)
        raise ValueError(f"Secret {secret_arn} must hold a JSON object")

    if not isinstance(payload, dict):
        logger.error("Secret %s is not a JSON object", secret_arn)
        raise ValueError(f"Secret {secret_arn} must hold a JSON object")

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


def reset_cache() -> None:
    """Drop the cached client and values. For tests."""
    global _client, _cache
    _client = None
    _cache = None
