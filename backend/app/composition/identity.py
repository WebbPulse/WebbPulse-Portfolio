"""The identity function's M1 composition: `IdentitySettings` and the package router.

## Why this lives in `app/composition/` rather than in `app/domains/identity/`

It is composition, not domain code, and the two boundary rules in
`tests/test_domain_boundaries.py` are what make that concrete. A module under
`app/domains/` may not import the composition root, and only a module that
declares routes may import FastAPI. This module does neither: it declares no
route of its own, it reads the product's `Settings`, and the router it returns
is the package's. Putting it beside the domain would have meant widening both
rules to accommodate one file, which retires the invariants they exist to hold.

The domain package keeps what is genuinely the domain's: `router.py` and its
`POST /login`. This module is the layer above, which is the layer that already
knows the process runs on Lambda with a role attached.

Section 6.2 of `docs/identity-standard.md` is the shape this follows. The product
builds an `IdentitySettings`, hands it to `build_identity_router`, and mounts the
result at the issuer's path. Everything the package fixes lives in the package;
everything this product owns stays here.

## What M1 mounts, and what it does not

`build_identity_router` in 0.9.0 serves exactly three routes:

    GET /.well-known/openid-configuration
    GET /.well-known/jwks.json
    GET /health

and nothing else. Login, refresh rotation, MFA, passkeys and OAuth are M2 and
later, per section 9.1. The existing `POST /api/v1/admin/login` is untouched by
this module and keeps working exactly as it did: it is a different router,
mounted at a different prefix, signing a different kind of token. The two coexist
until M2 replaces the second with the first, which is the whole reason M1 is
additive.

`hooks` and `stores` are not passed. The package accepts both and holds them
unused in 0.9.0, so passing them now would be writing a `PortfolioIdentityHooks`
whose every method is dead code until the milestone that calls it. Section 8.2
already records what those hooks will say for this product, which is the useful
half of writing them early.

## Where the router mounts, which is the issuer's path and not the origin

API Gateway builds the discovery URL by appending
`/.well-known/openid-configuration` to the configured issuer, path included. M0
proved it: an issuer of `https://api.staging.webbpulse.com` with no path produced
a create-time error naming
`https://api.staging.webbpulse.com/.well-known/openid-configuration`. The
standard's issuer carries a path, `https://<api host>/api/auth`, so the documents
have to answer under `/api/auth`.

`IdentitySettings` derives the same URLs the same way. Its `discovery_url` and
`jwks_url` are `f"{issuer}{PATH}"`, and the `jwks_uri` member the served
discovery document advertises is built from the issuer too. API Gateway follows
that `jwks_uri` literally rather than guessing, which M0's access log confirms,
so a document advertising a path the router does not serve fails
`CreateAuthorizer` at M2 just as a missing document does.

So `identity_mount_prefix` reads the path back off the issuer, and
`app/composition/wiring.py` mounts the router there. Deriving it rather than
writing `/api/auth` out in two places is what keeps the mount point and the
advertised URLs from drifting apart: change the issuer and both move together.
`terraform/apigateway.tf` carries route keys for the same two paths.

## Why the KMS client is constructed here

The package takes a KMS client rather than building one, which is what keeps
`boto3` out of the `identity` extra and keeps the module importable with no AWS
at all. Somebody has to construct it, and the composition root is the place: it
is the layer that already knows this process runs on Lambda with a role attached.

It is constructed lazily, inside `build_router`, rather than at import. Nothing in
this package calls AWS at import time, and a `boto3.client` at module scope would
be a credential resolution on every import of every module that transitively
reaches this one, including in a test suite that has no credentials.

The client is built once per process and shared, because `TokenService` caches
each key's public JWK for the life of the execution environment and a client per
request would not change that but would pay a fresh session setup each time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import APIRouter

    from .settings import Settings


def build_identity_settings(settings: Settings) -> Any:
    """`IdentitySettings` for this product, from the environment.

    Every field comes from an `IDENTITY_*` environment variable that
    `terraform/lambda_domains.tf` sets on the identity function, because
    `IdentitySettings` is a `BaseSettings` with `env_prefix="IDENTITY_"`. So this
    is a bare constructor call rather than a long keyword list: adding a setting
    is one line of Terraform and none of Python, which is the point of the
    prefix.

    That includes `IDENTITY_SIGNING_KEY_ARNS`, which Terraform renders as a JSON
    array. `IdentitySettings` deliberately refuses bare comma separated values
    for its list fields, so a stray comma in an ARN is an error here rather than
    a silently split entry.

    `settings` is taken as an argument rather than read from `get_settings()`
    inside, so a test can build this against a settings object it controls. It is
    currently unused, and that is deliberate rather than an oversight: every M1
    value reaches `IdentitySettings` through the environment directly, and
    reading a value here to pass it again would create a second path for the same
    string to travel and a second place for it to be wrong. The parameter stays
    because M2 needs it for `load_secrets`, and adding it later would change
    every call site.

    Raises `pydantic.ValidationError` when the environment is incomplete or
    inconsistent, which is what `check_required_secrets`-style fail-fast wants: a
    plaintext issuer outside local, a `SameSite=None` cookie without `Secure`, or
    an access token TTL over an hour all fail here, at startup, rather than on
    the first request that would have been affected.
    """
    from webbpulse.identity import IdentitySettings

    del settings  # See the docstring: M2's `load_secrets` is what needs it.
    return IdentitySettings()  # pyright: ignore[reportCallIssue]


def identity_mount_prefix(settings: Settings) -> str:
    """The path component of the issuer, which is where the router mounts.

    `https://api.staging.webbpulse.com/api/auth` gives `/api/auth`, and an issuer
    with no path gives `""`, which FastAPI takes as mounting at the root. Both
    are valid issuers; which one this product uses is Terraform's decision, and
    this follows it rather than restating it.

    The trailing slash is stripped because `include_router` rejects a prefix that
    ends in one, and because the standard warns that a trailing slash on the
    issuer is the classic way to produce a mismatch nothing logs.
    """
    from urllib.parse import urlsplit

    issuer = build_identity_settings(settings).issuer
    return urlsplit(str(issuer)).path.rstrip("/")


def build_router(settings: Settings) -> APIRouter:
    """The identity router, mounted at `identity_mount_prefix` by the caller."""
    import boto3
    from webbpulse.identity import build_identity_router

    from ..version import VERSION

    return build_identity_router(
        build_identity_settings(settings),
        kms_client=boto3.client("kms"),
        service="webbpulse-portfolio-identity",
        version=VERSION,
    )
