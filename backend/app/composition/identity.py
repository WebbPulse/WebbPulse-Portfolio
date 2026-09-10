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

## What M2 mounts, and what it does not

`build_identity_router` in 0.10.0 serves the three M1 documents:

    GET /.well-known/openid-configuration
    GET /.well-known/jwks.json
    GET /health

and, because this module now passes `hooks` and a `stores` carrying a credential
store, the six M2 flow routes as well:

    POST /register
    POST /login
    POST /password
    POST /refresh
    POST /logout
    POST /logout-all

all of them under the issuer's path, so `/api/auth/login` and the rest. The
mounting is conditional inside the package on exactly that pair being present,
which is why supplying them is the whole of what turns M2 on here.

MFA, passkeys and OAuth are M4 and later, per section 9.1.

**The existing `POST /api/v1/admin/login` is untouched.** It is a different
router in `app/domains/identity/router.py`, mounted at a different prefix, looking
the user up by username, and signing an HS256 token with a shared secret rather
than a KMS key. Nothing in this change removes it, redirects it, or alters what
it accepts. The two flows run side by side, which is what M2 adoption is: the
cutover that retires the legacy one is M9.

`hooks` is `PortfolioIdentityHooks` from `identity_hooks.py`. Section 8.2's
mapping, and that module's docstring, are where the policy is written down.

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

0.10.0 moved that derivation into the package: `build_identity_router` places
every route it declares under `identity_prefix(settings)`, which is the issuer's
path with any trailing slash stripped. So `app/composition/wiring.py` mounts the
router **with no prefix of its own**.

That is the breaking change in this bump, and it is the one this repository
reported. 0.9.0 served the documents at the origin whatever the issuer said, and
the workaround here was an `identity_mount_prefix` helper feeding
`include_router(..., prefix=...)`. Both are gone: leaving the prefix would double
every route to `/api/auth/api/auth/...`, and keeping the helper would be a second
implementation of a derivation the package now owns, which can only ever drift
from it. `terraform/apigateway.tf` carries route keys for the nine served paths.

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


def build_router(settings: Settings) -> APIRouter:
    """The identity router, mounted by the caller with no prefix of its own.

    `build_identity_router` places every route under the issuer's path itself.
    See the module docstring: a prefix here would double it.

    Passing `hooks` and a `stores` whose `credentials` is set is what mounts the
    six M2 flow routes; the package's mounting is conditional on exactly that
    pair, so omitting either would leave this serving the three M1 documents and
    nothing else.
    """
    import boto3
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import (
        DynamoCredentialStore,
        DynamoLoginAttemptStore,
        DynamoRefreshTokenStore,
        IdentityStores,
        build_identity_router,
    )

    from ..db.tables import CREDENTIALS, LOGIN_ATTEMPTS, REFRESH_TOKENS
    from ..version import VERSION
    from .identity_hooks import PortfolioIdentityHooks

    def repository(logical_name: str) -> Repository:
        """A package repository for one of the three M2 tables.

        Prefix and endpoint are passed explicitly rather than left to the
        package's environment lookup, so this reads the same `Settings` the rest
        of the backend does. `DYNAMODB_TABLE_PREFIX` is set on every function by
        `terraform/lambda_domains.tf` and would resolve identically, but the
        endpoint would not: `DYNAMODB_ENDPOINT_URL` is how a local run and the
        test suite point at something other than AWS, and the package reads no
        such variable.
        """
        return Repository(
            logical_name,
            prefix=settings.DYNAMODB_TABLE_PREFIX,
            endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
        )

    stores = IdentityStores(
        credentials=DynamoCredentialStore(repository(CREDENTIALS)),
        refresh_tokens=DynamoRefreshTokenStore(repository(REFRESH_TOKENS)),
    )

    return build_identity_router(
        build_identity_settings(settings),
        PortfolioIdentityHooks(),
        stores,
        kms_client=boto3.client("kms"),
        service="webbpulse-portfolio-identity",
        version=VERSION,
        # Progressive lockout. The package treats this as optional and runs the
        # flows with lockout disabled when it is absent, which is the right
        # default for a product that has not created the table. This one has, in
        # the same apply that creates the other two, so there is no window where
        # passing it would fail.
        attempts=DynamoLoginAttemptStore(repository(LOGIN_ATTEMPTS)),
    )
