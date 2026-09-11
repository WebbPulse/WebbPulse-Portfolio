"""Reading the identity access token's claims, in whichever shape they arrive.

`app/core/security.py`'s `get_current_user` calls this after the legacy HS256
token fails to resolve. Nothing here mints and nothing here decides policy. It
answers one question, "which subject did an authorizer verify for this request,
if any", and answers it with `None` rather than an exception for every way the
answer can be "nobody".

## Two shapes, one reader

The same access token reaches this application through two different paths, and
which one applies is a deployment fact rather than a request fact:

1. **Production, once `identity_jwt_mode` is "native".** API Gateway's own JWT
   authorizer verifies the token and puts the claims at
   `requestContext.authorizer.jwt.claims`, as a flat string map. Every value is
   a string there, `exp` included.
2. **Staging today, where `identity_jwt_mode` is "gate".** Every route carries
   the staging access gate's REQUEST authorizer, and an HTTP API route takes
   exactly one authorizer, so the gate's own Lambda does the verification on the
   flagged route keys. A Lambda authorizer's context always lands under
   `requestContext.authorizer.lambda` and API Gateway refuses a nested object
   there, so the gate publishes one string key literally named `jwt.claims`
   holding the claims as JSON. The values inside it are stringified too,
   deliberately, so that `exp` reads the same way in both environments and no
   caller needs a branch on which environment it is in.

Either way the request context reaches this process in the
`x-amzn-request-context` header, which the Lambda Web Adapter writes from the
invoke event as plain JSON rather than base64.

`webbpulse.identity.claims.read_authorizer_claims` is the package's reader and
it handles shape 1 only: it raises `NoClaimsSection` for a context whose
`authorizer` has `lambda` rather than `jwt`. So this module calls it first and
falls back to the gate's shape, rather than reimplementing the part the package
already owns. `coerce_claims` is the package's too, and running the gate's JSON
through it is what makes the two shapes produce identical Python values rather
than merely similar ones.

## Why this does not verify a signature

On a flagged route key the token was verified before this process was invoked,
by the gateway's JWT authorizer in production or by the gate's Lambda in
staging. Verifying it a second time here would be a `kms:GetPublicKey` and a
signature check per request to reach an answer that is already in the event, and
it would need a KMS grant this function does not have and is not being given.

**The claims are trusted only because of where they arrive.** The
`x-amzn-request-context` header is written by the Lambda Web Adapter from the
invoke event; an inbound header of that name from a caller never reaches it,
because API Gateway does not forward it and the adapter overwrites it from the
event regardless. A caller therefore cannot fabricate a claims section, and a
request that carries no authorizer section is not a failed authorization, it is
a route that was never configured to carry one.

## Why a failed read is indistinguishable from no token

Every path below answers `None`, and `get_current_user` turns `None` into the
same 401 the legacy token already produces. A claims section naming a subject
that resolves to no row, a subject that is not one of this product's integer
ids, and no claims at all are one answer to a caller, because distinguishing
them is a signal handed to somebody probing.
"""

import json
from collections.abc import Mapping
from typing import Any, Optional

from fastapi import Request

from .logging import logger

__all__ = ["GATE_CLAIMS_KEY", "identity_claims", "identity_subject"]

#: The single context key the staging access gate's Lambda authorizer publishes,
#: holding every claim as JSON. Named `jwt.claims` with a literal dot so that the
#: value sits at `authorizer.lambda["jwt.claims"]` and mirrors the native
#: authorizer's `authorizer.jwt.claims` as closely as a Lambda authorizer can.
#: The gate also lifts `jwt.claims.sub`, `jwt.claims.iss` and `jwt.claims.exp`
#: out as their own keys; this module reads the JSON rather than the lifted
#: subject, so one code path produces the whole claim set in both environments
#: and a caller that later wants `roles` does not need a second reader.
GATE_CLAIMS_KEY = "jwt.claims"


def _gate_claims(request: Request) -> Optional[dict[str, Any]]:
    """The gate authorizer's claims for this request, or `None`.

    Reached only when the package's reader found no `authorizer.jwt.claims`,
    which in staging is every flagged request. The header is parsed a second
    time rather than threaded out of the package's reader because the package
    raises before it returns anything on this shape, and parsing a header this
    process already holds in memory is cheaper than vendoring the package's
    parse to reach its intermediate value.

    Answers `None` for every failure and logs the one worth seeing. An
    unparseable `jwt.claims` is worth seeing because the gate writes it with
    `JSON.stringify` and nothing else writes it at all, so a value that does not
    parse means the two sides disagree about the encoding.
    """
    from webbpulse.http import REQUEST_CONTEXT_HEADER

    raw = request.headers.get(REQUEST_CONTEXT_HEADER)
    if raw is None or not raw.strip():
        return None
    try:
        context = json.loads(raw)
    except ValueError:
        # The package's reader has already logged and raised on this, so debug
        # here rather than a second warning for one header.
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
        # A gate authorizer that ran and allowed the request on a route key that
        # is not flagged publishes no claims at all, which is the ordinary state
        # of an unflagged request and not worth a log line.
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

    Tries the native authorizer's shape through the package's own reader first,
    then the staging gate's. Both results go through the package's coercion, so
    `exp` is an `int` and `roles` is a `list[str]` whichever environment
    produced them: the gate stringifies every value on purpose so exactly this
    is possible.

    `None` means no authorizer put claims on this route, which is not the same
    thing as a refused request. See the module docstring.
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

    `sub` is the Portfolio user id as a string. `PortfolioIdentityHooks.
    claims_for` puts only `roles` in the token and leaves `sub` to the package,
    which sets it from the user row's `id`, so the mapping from a token to a row
    is the id and there is no link table between them.
    """
    claims = identity_claims(request)
    if claims is None:
        return ""
    return str(claims.get("sub", "") or "")
