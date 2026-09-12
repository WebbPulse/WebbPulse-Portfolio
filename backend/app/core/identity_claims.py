"""Reading the identity access token's claims, in whichever shape they arrive.

The native JWT authorizer and the staging gate's Lambda authorizer publish the
same claims differently. Nothing here verifies a signature.
"""

import json
from collections.abc import Mapping
from typing import Any, Optional

from fastapi import Request

from .logging import logger

__all__ = ["GATE_CLAIMS_KEY", "identity_claims", "identity_subject"]

GATE_CLAIMS_KEY = "jwt.claims"
"""The single context key the staging access gate's Lambda authorizer publishes,
holding every claim as JSON. The literal dot mirrors the native authorizer's
`authorizer.jwt.claims` as closely as a Lambda authorizer can."""


def _gate_claims(request: Request) -> Optional[dict[str, Any]]:
    """The gate authorizer's claims for this request, or `None`.

    Reached only when no native claims section was found. Answers `None` for every
    failure, warning only on a value the gate wrote that will not parse.
    """
    from webbpulse.http import REQUEST_CONTEXT_HEADER

    raw = request.headers.get(REQUEST_CONTEXT_HEADER)
    if raw is None or not raw.strip():
        return None
    try:
        context = json.loads(raw)
    except ValueError:
        logger.debug("Request context header is not JSON")
        return None
    if not isinstance(context, Mapping):
        return None

    authorizer = context.get("authorizer")
    if not isinstance(authorizer, Mapping):
        return None
    lambda_context = authorizer.get("lambda")
    if not isinstance(lambda_context, Mapping):
        return None
    encoded = lambda_context.get(GATE_CLAIMS_KEY)
    if not isinstance(encoded, str) or not encoded.strip():
        return None
    try:
        claims = json.loads(encoded)
    except ValueError:
        logger.warning(
            "Staging access gate published an unparseable claims context value",
            extra={"key": GATE_CLAIMS_KEY},
        )
        return None
    if not isinstance(claims, Mapping):
        return None
    return dict(claims)


def identity_claims(request: Request) -> Optional[Mapping[str, Any]]:
    """The verified identity claims for this request, or `None` for none.

    Tries the native authorizer's shape first, then the gate's, coercing both.
    `None` means no authorizer ran, which is not a refused request.
    """
    from webbpulse.identity.claims import (
        ClaimsUnavailable,
        coerce_claims,
        read_authorizer_claims,
    )

    try:
        return read_authorizer_claims(request)
    except ClaimsUnavailable:
        pass
    gate = _gate_claims(request)
    if gate is None:
        return None
    return coerce_claims(gate)


def identity_subject(request: Request) -> str:
    """The verified `sub` an authorizer put on this request, or `""`.

    `sub` is the Portfolio user id as a string, so a token maps to a row by id
    with no link table between them.
    """
    claims = identity_claims(request)
    if claims is None:
        return ""
    return str(claims.get("sub", "") or "")
