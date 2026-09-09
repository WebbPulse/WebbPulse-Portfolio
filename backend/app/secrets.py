"""Read the application's secrets from AWS Secrets Manager, lazily and cached.

One secret per service per environment: `APP_SECRETS_ARN` names a single
Secrets Manager secret whose string is a JSON object, and its keys are the
settings names the application expects, SECRET_KEY, ADMIN_USERNAME,
ADMIN_PASSWORD and ADMIN_EMAIL. That is the shape the app-secrets Terraform
module's `json` field creates.

**The fetch, the parse and the cache now come from `webbpulse.config`.** This
module used to carry its own boto3 client, its own `json.loads`, its own
validation of the three ways a secret can be unusable, and its own module level
`_cache` dict. All four are `load_json_secret` in the shared package, cached per
ARN with an `lru_cache`, so the copy here was a second implementation of a
solved problem that could drift from the one CarModPicker runs. What is left is
the part that is genuinely Portfolio's: flattening the object to strings, which
is what `Settings` assigns into four `Optional[str]` fields.

Nothing here runs at import. The client is built on first use inside the shared
package and the blob is fetched on the first read of a secret field, which is
what lets `public` import the application with no Secrets Manager grant at all
and what keeps the suite and a local checkout free of AWS.

The blob is fetched once per execution environment, so a warm Lambda invocation
makes no Secrets Manager call. No value is ever logged: the log line below names
the keys and counts them, never their contents.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from webbpulse.config import load_json_secret, reset_secret_cache

logger = logging.getLogger(__name__)

# Portfolio's own flattening of the shared loader's result, cached separately
# from it. `load_json_secret` caches the parsed object; this caches the string
# map built from it, so repeated reads do neither the fetch nor the flatten.
_cache: Optional[dict[str, str]] = None


def load_app_secrets(secret_arn: str, client: Any = None) -> dict[str, str]:
    """Return the secret's JSON object as a flat map of strings.

    Anything that stops the blob being read is fatal: a denied read, a missing
    secret, a secret with no version, a body that is not JSON, a JSON document
    that is not an object. All of them mean the function is misconfigured and
    must fail at cold start rather than start up without a signing key. The
    shared loader raises botocore's own error for the first two and
    `SecretNotJsonObjectError`, a `ValueError`, for the rest, which is the same
    distinction this module used to draw itself.

    Values that are not strings are JSON-encoded so the caller always gets
    strings; null values are dropped, which is how the module represents
    "absent".

    `client` is accepted for the tests that pass an explicit Secrets Manager
    client. The shared loader builds and caches its own, so a client given here
    is used directly and its result is not put in the shared cache, which keeps
    an injected client from leaking into a later call that did not ask for one.
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

    `load_json_secret` owns its client so it can cache one per process, which
    leaves no seam for an injected one. Rather than reach into that cache, this
    repeats the three checks against the given client and raises the same
    `ValueError` the shared loader raises, so the two paths agree on what an
    unusable secret is.
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
        raise ValueError(
            f"Secret {secret_arn} parsed as {type(payload).__name__}, "
            "expected a JSON object."
        )
    return payload


def reset_cache() -> None:
    """Drop the cached values, here and in the shared loader. For tests.

    Both halves, because the shared cache holds the parsed object this one is
    derived from: clearing only the local map would refill it from a stale
    parse and a rotation test would still see the old value.
    """
    global _cache
    _cache = None
    reset_secret_cache()
