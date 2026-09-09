"""The identity standard's M0 spike, and nothing else.

**This module is throwaway.** Milestone M0 of `docs/identity-standard.md` in the
webbpulse-python repository exists to answer one question with a real API
Gateway rather than with reading: does an HTTP API JWT authorizer verify an
RS256 token signed by a real KMS asymmetric key, against a JWKS and an OIDC
discovery document served by this process? Every milestone after it assumes yes.
When the answer is in hand, this file is deleted; nothing in the application is
built on top of it and nothing should be.

Three routes, and only when `IDENTITY_SPIKE_ENABLED` is set. Terraform writes
that variable onto the staging identity function only, gated behind
`var.identity_spike_enabled`, which defaults to false, so production and any
workspace that has not opted in never construct this router at all.

The two `.well-known` documents come from `webbpulse.identity`'s own router and
are not declared here. They mount at the origin, with no `/api/v1` prefix,
because RFC 8615 puts `.well-known` at the root of an origin and the authorizer
derives their URLs from the issuer, which is the origin. `app/composition/wiring.py`
is where that mounting happens, and it is deliberately not part of the domain's
prefixed router.

What is declared here is the two ends of the experiment:

- `POST /api/identity/spike/token` mints a token. It is behind the staging
  access gate like everything else in the application, and it authenticates
  nobody: any caller past the gate gets a signed token for whatever subject they
  ask for. Declaring the handler here is only half of that: the route key has to
  be in `apigateway.tf`'s routes map for a request to reach this process at all,
  and it was missing from the map when the spike first went live, which made the
  endpoint API Gateway's own 404 and left no way to obtain a token to point at
  `whoami`. **That is why the whole spike is gated and why it is throwaway.** A
  route that mints a valid access token for an arbitrary subject is the exact
  shape of the bug the real design exists to prevent, and it is acceptable here
  only because the gate stands in front of it, the environment is staging, and
  the route is deleted with the rest of this file. The package refuses to mint
  at all when `ENVIRONMENT` is production, which is a second independent gate.

- `GET /api/identity/spike/whoami` is protected by the JWT authorizer rather
  than by the gate, and it is the actual measurement. It reads the claims out of
  the request context and returns them. **It performs no verification of its
  own, and that is the point**: if this handler runs at all, API Gateway already
  fetched the JWKS, verified an RS256 signature that KMS produced, and matched
  the issuer and the audience. A 200 from it is the proof. A 401 from API
  Gateway with no token, which never reaches this handler, is the other half.

One result is already in, and it is the one that made the first apply fail:
**API Gateway validates a JWT authorizer's issuer when the authorizer is
created.** CreateAuthorizer fetches `<issuer>/.well-known/openid-configuration`
synchronously and refuses the call with a BadRequestException, "Issuer must have
a valid discovery endpoint", when it does not get a discovery document back.

That is a fact about deployment order, not about this file, but it is what makes
this file load-bearing at apply time rather than only at request time. This
process must already be serving the discovery document, through a route that is
already reachable anonymously, before the authorizer that protects `whoami` can
exist at all. `terraform/identity_spike.tf` carries the ordering that guarantees
it: the two `.well-known` routes stay in `apigateway.tf`'s routes map, next to
the gated mint route, which names no authorizer and so constrains nothing;
`whoami` is a standalone route created after the authorizer, and the authorizer
waits on both modules plus a poll of the live URL. Switching
`IDENTITY_SPIKE_ENABLED` off and on again is therefore not a runtime toggle for
an environment that already has the authorizer; it is the thing the authorizer
was built on top of.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from ...config import get_settings

#: Where the Lambda Web Adapter puts the API Gateway request context. The
#: adapter turns an invoke into an ordinary HTTP request against 127.0.0.1 and
#: passes the event's `requestContext` through as this header, base64-encoded
#: JSON. Section 2.4 of the standard describes reading it; there is no
#: `authorizer_claims` helper in webbpulse 0.6.0 to call, so the spike reads the
#: header itself and M1 decides where the shared version of this belongs.
REQUEST_CONTEXT_HEADER = "x-amzn-request-context"

router = APIRouter()


def _request_context(request: Request) -> dict[str, Any]:
    """The API Gateway request context, or an empty mapping.

    Every failure mode here returns empty rather than raising. The header is
    absent when the process is run directly rather than under the adapter, and
    a malformed one is not something a handler can do anything useful about. The
    caller turns empty into a 401, which is the honest answer either way: the
    claims could not be read, so the request is not authorized.
    """
    raw = request.headers.get(REQUEST_CONTEXT_HEADER)
    if not raw:
        return {}
    try:
        # The header is base64 without padding in some adapter versions, so the
        # padding is restored rather than assumed. `validate=False` would hide a
        # genuinely corrupt value, which is why it is left strict.
        padded = raw + "=" * (-len(raw) % 4)
        decoded = json.loads(base64.b64decode(padded))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


@router.get("/whoami")
async def whoami(request: Request) -> dict[str, Any]:
    """Return the claims API Gateway's JWT authorizer put in the request context.

    Reached only through `GET /api/identity/spike/whoami`, whose route key
    carries `authorization_type = "JWT"` and this API's own JWT authorizer. So
    by the time this function runs, the gateway has already done everything the
    spike is measuring.

    The raw context is returned alongside the claims on purpose. Which shape the
    authorizer actually produces, `authorizer.jwt.claims` as the documentation
    describes it or something else under a payload format version this API did
    not choose, is one of the things the spike is here to observe, and guessing
    wrong would turn a successful verification into an empty 200 that looks like
    a failure.
    """
    context = _request_context(request)
    authorizer = context.get("authorizer")
    authorizer = authorizer if isinstance(authorizer, dict) else {}
    jwt_context = authorizer.get("jwt")
    jwt_context = jwt_context if isinstance(jwt_context, dict) else {}
    claims = jwt_context.get("claims")
    claims = claims if isinstance(claims, dict) else {}

    if not claims:
        # Not reachable through the gateway, which denies before invoking, so
        # this fires when the function is called some other way: directly, or
        # through a route whose authorization is not what this handler assumes.
        # Answering 401 rather than 200-with-nothing keeps a misrouted request
        # from reading as a successful verification of no one.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "No JWT claims in the request context. This route is only "
                "meaningful behind the API Gateway JWT authorizer."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "claims": claims,
        # Named so a reader of the response can tell which of the two questions
        # from section 10 the run answered without going to the access log.
        "authorizer_context_keys": sorted(authorizer),
        "request_context_keys": sorted(context),
    }


@router.post("/token", status_code=status.HTTP_201_CREATED)
async def mint(subject: str = "spike") -> dict[str, Any]:
    """Mint an RS256 token signed by KMS. Staging only, authenticates nobody.

    See the module docstring for why a route like this is acceptable here and
    nowhere else. Three independent things have to be true for it to run: the
    router is only constructed when `IDENTITY_SPIKE_ENABLED` is set, the package
    refuses to mint when `ENVIRONMENT` is production, and the whole Terraform
    stack behind it is off by default.
    """
    from webbpulse.identity import mint_test_token

    settings = get_settings()
    key_id = settings.IDENTITY_SIGNING_KEY_ID
    issuer = settings.IDENTITY_TOKEN_ISSUER
    audience = settings.IDENTITY_TOKEN_AUDIENCE
    if not (key_id and issuer and audience):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The identity spike is enabled but not configured. "
                "IDENTITY_SIGNING_KEY_ID, IDENTITY_TOKEN_ISSUER and "
                "IDENTITY_TOKEN_AUDIENCE all have to be set."
            ),
        )

    token = mint_test_token(
        _signer(key_id),
        enabled=True,
        environment=settings.ENVIRONMENT,
        issuer=issuer,
        audience=audience,
        subject=subject,
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": 600}


def _signer(key_id: str) -> Any:
    """One `KmsSigner` per key id, per execution environment.

    Constructing a signer calls `kms:GetPublicKey` once, because the `kid` is
    derived from the key material rather than from the key id. Caching it means
    a cold start pays that call once instead of every mint paying it, which
    matters for the same reason it will matter in the real thing: the `kid` is
    stable for as long as the key material is, and this design never mutates key
    material behind a key id.
    """
    global _SIGNER
    if _SIGNER is None or _SIGNER.key_id != key_id:
        import boto3
        from webbpulse.identity import KmsSigner

        _SIGNER = KmsSigner(boto3.client("kms"), key_id)
    return _SIGNER


_SIGNER: Any = None
