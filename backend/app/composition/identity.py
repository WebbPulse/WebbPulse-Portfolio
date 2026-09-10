"""The identity function's composition: `IdentitySettings` and the package router.

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

## What M4 mounts, and what it does not

`build_identity_router` in 0.13.0 serves the three M1 documents:

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

and, because this module now also passes an `email_sender` and a `stores`
carrying an `identity-tokens` store, the four M3 email routes:

    POST /verify-email
    POST /verify-email/confirm
    POST /reset
    POST /reset/confirm

and, because this module now also passes a `stores` carrying a TOTP factor
store and a recovery code store on top of the identity-tokens store M3 already
supplied, the six M4 MFA routes:

    POST /login/totp
    POST /totp/enrol
    POST /totp/activate
    POST /totp/disable
    POST /recovery-codes
    POST /step-up

`totp/disable` and `recovery-codes` take a required `{"code": "..."}` body as of
0.13.0, where both previously acted on the bearer subject alone. The code is a
current TOTP code or an unused recovery code, it is verified before either route
deletes anything, and a recovery code spent on either is consumed exactly as it
is on login. A missing or blank one is a 422 `VALIDATION_ERROR` and a wrong one
a 401 `INVALID_MFA_CODE`. Both routes now carry the same `mfa-verify` rate limit
as `login/totp`, because they accept the same codes. Nothing in this module
changes for that: the body is the package's contract with the caller, and the
frontend is what sends it.

all of them under the issuer's path, so `/api/auth/login` and the rest. Each
group's mounting is conditional inside the package on exactly its own
collaborators being present, which is why supplying them is the whole of what
turns M2, M3 and M4 on here. The M3 pair is a sender and the token store, and
`build_email_sender` below returns `None` where SES does not exist, which leaves
the four email routes undeclared rather than declared and answering 503. M4's
condition is `totp_enabled` plus all three of the factor store, the recovery
code store and the token store, which this module now supplies unconditionally.

## What M4 changes about a login, which is nothing until somebody enrols

The package answers `login` with a challenge rather than tokens **only for a
user with an active TOTP factor**: 200 and
`{"mfa_required": true, "mfa_ticket": "...", "factors": ["totp"]}`, which the
caller finishes at `POST /api/auth/login/totp` with `{"mfa_ticket", "code"}`.
Nobody is enrolled, so today every login answers exactly as it did under 0.11.0
and the shape changes for one administrator on the day they enrol.

`login/totp` is the one M4 route that is anonymous to the identity JWT
authorizer, and it has to be: the ticket's audience is `<issuer>/mfa` rather
than the API audience, so a JWT authorizer configured with the API audience
rejects the second leg of every MFA login before it runs. It still sits behind
the staging access gate like every other flow route, which is a different
control; `terraform/apigateway.tf` has the full note.

## Where the envelope cipher comes from, which is one environment variable

A TOTP seed is the one identity secret that cannot be hashed: the server has to
reproduce the code to check it, so unlike a password there is no one-way form.
`webbpulse.identity.crypto.EnvelopeCipher` therefore seals it under a data key
that KMS mints, and the key it mints from is `IDENTITY_DATA_KEY_ARN`, which
`module.identity` sets on this function from the symmetric envelope key it
creates. Nothing here reads that variable by hand. `IdentitySettings` picks it
up under the `IDENTITY_` prefix as `data_key_arn`, and `MfaService` builds the
cipher from it and from the same KMS client this module already passes for
signing, on the first enrolment rather than at construction.

That is why there is no new argument below. The cipher is wired by the variable
existing and by `kms_client` already being passed, and when the variable is
absent enrolment fails loudly with a message naming it rather than storing a
seed in the clear.

## What M6 mounts, and why it mounts nothing today

`build_identity_router` in 0.14.0 also declares five OAuth routes:

    GET    /oauth/{provider}/start
    GET    /oauth/callback
    POST   /oauth/{provider}/link
    GET    /oauth/links
    DELETE /oauth/{provider}/link

**and it declares none of them in either environment right now.** The package's
condition is two things at once: a `stores` carrying both `oauth_states` and
`oauth_links`, which this module supplies unconditionally below, AND at least
one provider carrying a client id, which is
`OAuthService.enabled_providers()`. The client ids come from
`IDENTITY_GOOGLE_CLIENT_ID` and `IDENTITY_GITHUB_CLIENT_ID`, which
`terraform/identity.tf` renders from variables that default to empty, and no
OAuth app has been registered with Google or GitHub yet. So the list is empty
and the five routes are not in the OpenAPI document.

That is the package's own rule rather than a workaround here, and its changelog
states it: a route that could only answer 503 because nobody set a client id is
worse than a route that does not exist. It is also what makes this adoption safe
to deploy ahead of the owner doing anything. The two tables are created, two
stores are constructed, three environment variables are set, and the served API
is byte identical to what 0.13.0 served.

Switching a provider on later is configuration and not code: one HCP Terraform
variable for the client id, one key in the `webbpulse-<env>/app` secret for the
client secret, and a redeploy. `docs/identity-cutover.md` lists exactly what has
to be registered with each provider.

## Where the OAuth client secrets come from, which is not the environment

The two client ids are ordinary `IDENTITY_*` environment variables, because a
client id is not a secret: it travels in the authorization URL in the user's own
browser on every sign in. The two client secrets are not, and they are not
settings either. They are keys of the single `webbpulse-<env>/app` secret and
they reach the package as the `oauth_client_secrets` argument to
`build_identity_router`, built by `build_oauth_client_secrets` below.

The package takes them as an argument rather than as an `IdentitySettings` field
deliberately, and its reasoning is the same rule the settings module states for
itself: a secret that is a settings field is a secret that appears in a `repr`,
in a pydantic validation error and in whatever log line prints the settings
object. Everything else about that decision is in that function's docstring,
including why an empty mapping is a success rather than a failure.

## The one hook M6 adds, which has a default the product should not take

`IdentityHooks.has_other_sign_in_method(user_id)` is new in 0.14.0 and it is the
first hook since M3 to change the protocol. It defaults to `False` on
`BaseIdentityHooks`, so a product that inherits from that class keeps working
untouched. `PortfolioIdentityHooks` does not inherit from it, it satisfies the
protocol structurally, so it would have stopped satisfying the protocol without
the method; `tests/test_identity_m2.py`'s `isinstance` check against the runtime
checkable `Protocol` is what would have caught that.

It is implemented rather than left to a default because the default's whole
point is to be conservative in one direction, and Portfolio can answer the
question exactly. `identity_hooks.py` has the reasoning.

## What M5 mounts, and why it mounts nothing today

`build_identity_router` in 0.15.0 also declares seven passkey routes:

    POST   /passkeys/register/options
    POST   /passkeys/register/verify
    POST   /login/passkey/options
    POST   /login/passkey/verify
    GET    /passkeys
    PATCH  /passkeys/{credential_id}
    DELETE /passkeys/{credential_id}

**and it declares none of them in either environment right now**, on exactly the
shape M6's OAuth routes follow. The package's condition is three things at once:
a `stores` carrying both `passkeys` and `webauthn_challenges`, which this module
supplies unconditionally below, AND `passkeys_enabled` on the settings.
`terraform/lambda_domains.tf` renders that last one from a variable defaulting to
false, so the list of mounted routes is unchanged and the served API is byte
identical to what 0.14.0 served.

**The package's own default for both passkey flags is `True`, and this product
ships them false.** That inversion is the one thing about this adoption worth
reading twice, because it means an omitted environment variable is not a
no-op here: it would mount seven routes. The package defaults them on because
the standard treats the baseline as mandatory and the flags exist to stage a
rollout rather than to opt out permanently, which is precisely what this is, and
staging it is why `IDENTITY_PASSKEYS_ENABLED` is set explicitly rather than left
to the default. The frontend has no passkey code until `@webbpulse/auth` 0.8.0,
so a mounted route today is a route nothing calls and one that a curious client
could enrol a credential against, against an RP id that is immutable for that
credential's life.

Switching passkeys on later is configuration and not code: one HCP Terraform
variable per environment and a redeploy. `docs/identity-cutover.md` has the
sequence.

## The second flag, which stays off after the first one goes on

`passkeys_passwordless` is a separate switch and is deliberately not the same
one. With `passkeys_enabled` true and `passkeys_passwordless` false, all five
management routes mount and both `/login/passkey/*` routes refuse: a passkey is
a credential a user can enrol, list, rename and delete, and a second factor, but
not an entry point. Turning it on makes a passkey a way into the account with no
password at all.

That is a policy decision rather than a rollout step, which is why it has its own
variable and why it stays false until the owner decides. The package's own note
is that `POST /login/passkey/options` answers any input, including an unknown
address, returning a challenge and an empty `allowCredentials` so the anonymous
route cannot become an account oracle. That property is what makes passwordless
safe to turn on; it is not what makes it the right choice for a single
administrator product, and nothing here presumes on that.

## Where the RP id and the origins come from, and why both are required

`rp_id` is the registrable domain, hashed into every credential and immutable
for that credential's life, so it is the one identity setting that cannot be
corrected later without invalidating every passkey enrolled under the old value.
It arrives as `IDENTITY_RP_ID` from `module.identity`, which takes it as
`registrable_domain` and refuses a URL, and it is the same string the refresh
cookie is scoped to. Nothing here sets it.

`IDENTITY_WEBAUTHN_ORIGINS` is this product's, and it is a JSON array because
`IdentitySettings.webauthn_origins` is a list field and the class refuses bare
comma separated values for those, the same rule `IDENTITY_SIGNING_KEY_ARNS` and
`IDENTITY_OAUTH_REDIRECT_URIS` follow. It carries the frontend origin, derived
in Terraform from the same `local.domain` that `IDENTITY_FRONTEND_BASE_URL` is
built from, so the origin a browser sends and the origin the ceremony checks
cannot drift apart.

The package requires both rather than defaulting either, and raises naming the
variable when one is missing. That is the right severity: an empty origin list
makes the origin check vacuous, and the origin check is the whole of what makes
a passkey phishing resistant.

## What M5 does not change, which is the hooks

`IdentityHooks` is byte identical in 0.15.0 to what it was in 0.14.0. M5 adds no
hook method, so `PortfolioIdentityHooks` satisfies the protocol untouched, and
`tests/test_identity_m2.py`'s `isinstance` check against the runtime checkable
`Protocol` is what proves that rather than a claim about it.

The rule the package could have asked a hook for and did not is that the last
passkey cannot be deleted by a user with no password. It reads "has a password"
from the `credentials` store, which is where this package's own password lives,
so it needs nothing from the product. A product whose users can sign in some way
the package cannot see still has `may_authenticate` and `has_other_sign_in_method`
to refuse the delete in front of the route; Portfolio's answer to the latter is
already `False` and is unchanged by M5.

**The existing `POST /api/v1/admin/login` is untouched.** It is a different
router in `app/domains/identity/router.py`, mounted at a different prefix, looking
the user up by username, and signing an HS256 token with a shared secret rather
than a KMS key. Nothing in this change removes it, redirects it, or alters what
it accepts. The two flows run side by side, which is what M2 and M3 adoption is:
the cutover that retires the legacy one is M9.

`hooks` is `PortfolioIdentityHooks` from `identity_hooks.py`. Section 8.2's
mapping, and that module's docstring, are where the policy is written down. M3
added one hook to it, `mark_email_verified`, which is the only hook the package
gives no default. **M4 adds none.** The hooks protocol is byte identical in
0.13.0 to what it was in 0.11.0, so `PortfolioIdentityHooks` satisfies it
unchanged, and `tests/test_identity_m2.py`'s structural `isinstance` check
against the runtime checkable `Protocol` is what proves that rather than a claim
about it.

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

## Why the KMS and SES clients are constructed here

The package takes a KMS client rather than building one, and `SesV2EmailSender`
takes an SES client on the same terms, which is what keeps `boto3` out of the
`identity` extra and keeps the module importable with no AWS at all. Somebody
has to construct them, and the composition root is the place: it is the layer
that already knows this process runs on Lambda with a role attached.

Both are constructed lazily, inside a function, rather than at import. Nothing in
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
    six M2 flow routes. Passing an `email_sender` **and** a `stores` whose
    `identity_tokens` is set is what mounts the four M3 routes on top; the
    package's mounting is conditional on exactly those pairs, so omitting either
    half of either pair leaves the rest serving unchanged.

    M4's six MFA routes are the same rule with a longer condition: `totp_enabled`
    on the settings, which is the package's default, plus all three of
    `totp_factors`, `recovery_codes` and `identity_tokens` on the stores. All
    three are supplied below, so all six mount. They need no argument of their
    own: the envelope cipher is built inside `MfaService` from
    `IDENTITY_DATA_KEY_ARN` and the `kms_client` already passed here.

    M6's five OAuth routes are the same rule again, and the half of the
    condition this module does not control is what leaves them unmounted.
    Supplying `oauth_states` and `oauth_links` is necessary and not sufficient:
    the package also needs `enabled_providers()` to be non-empty, which needs a
    client id from the environment, and neither is set. So the two stores below
    and the `oauth_client_secrets` argument are both live wiring against a
    switch that is currently off. See the module docstring.

    M5's seven passkey routes are the same rule once more. Supplying `passkeys`
    and `webauthn_challenges` is necessary and not sufficient: the package also
    needs `passkeys_enabled`, which comes from `IDENTITY_PASSKEYS_ENABLED` and
    is false in both environments. The two stores below are live wiring against
    a switch that is off, and unlike M6's the package's own default for that
    switch is on, so it is set explicitly rather than omitted. See the module
    docstring.
    """
    import boto3
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import (
        DynamoCredentialStore,
        DynamoIdentityTokenStore,
        DynamoLoginAttemptStore,
        DynamoOAuthLinkStore,
        DynamoOAuthStateStore,
        DynamoPasskeyStore,
        DynamoRecoveryCodeStore,
        DynamoRefreshTokenStore,
        DynamoTotpFactorStore,
        DynamoWebAuthnChallengeStore,
        IdentityStores,
        build_identity_router,
    )

    from ..db.tables import (
        CREDENTIALS,
        IDENTITY_TOKENS,
        LOGIN_ATTEMPTS,
        OAUTH_LINKS,
        OAUTH_STATES,
        PASSKEYS,
        RECOVERY_CODES,
        REFRESH_TOKENS,
        TOTP_FACTORS,
        WEBAUTHN_CHALLENGES,
    )
    from ..version import VERSION
    from .identity_hooks import PortfolioIdentityHooks

    def repository(logical_name: str) -> Repository:
        """A package repository for one of the ten identity tables.

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

    identity_settings = build_identity_settings(settings)

    stores = IdentityStores(
        credentials=DynamoCredentialStore(repository(CREDENTIALS)),
        refresh_tokens=DynamoRefreshTokenStore(repository(REFRESH_TOKENS)),
        identity_tokens=DynamoIdentityTokenStore(repository(IDENTITY_TOKENS)),
        # M4. Supplying these two, with `identity_tokens` already above and
        # `totp_enabled` left at the package's default, is the whole of what
        # mounts the six MFA routes. The MFA ticket that carries a login between
        # its two legs is an `identity-tokens` row with
        # `purpose = "mfa_ticket"`, so it needs no store of its own.
        totp_factors=DynamoTotpFactorStore(repository(TOTP_FACTORS)),
        recovery_codes=DynamoRecoveryCodeStore(repository(RECOVERY_CODES)),
        # M6. Supplied unconditionally, which is deliberate and is NOT what
        # decides whether the OAuth routes exist. The package's condition is
        # both stores AND at least one provider carrying a client id, so with
        # `IDENTITY_GOOGLE_CLIENT_ID` and `IDENTITY_GITHUB_CLIENT_ID` both
        # empty, which is how they ship, `enabled_providers()` is empty and no
        # OAuth route is declared. These two stores then cost one `Repository`
        # construction each and touch DynamoDB not at all: a `Repository`
        # resolves its table lazily per call.
        #
        # Supplying them unconditionally rather than behind a check on the ids
        # keeps the switch in exactly one place. The ids come from Terraform
        # variables, and having the routes turn on when an id appears, with no
        # second condition here that could disagree, is what makes registering
        # an OAuth app a configuration change rather than a code change.
        oauth_states=DynamoOAuthStateStore(repository(OAUTH_STATES)),
        oauth_links=DynamoOAuthLinkStore(repository(OAUTH_LINKS)),
        # M5. Supplied unconditionally, on exactly the reasoning the M6 pair
        # above carries, and NOT what decides whether the passkey routes exist.
        # The package's condition is both stores AND `passkeys_enabled`, and
        # `IDENTITY_PASSKEYS_ENABLED` is false in both environments, so no
        # passkey route is declared. These two stores then cost one `Repository`
        # construction each and touch DynamoDB not at all: a `Repository`
        # resolves its table lazily per call.
        #
        # Supplying them unconditionally rather than behind a check on the flag
        # keeps the switch in exactly one place. A second condition here could
        # only ever disagree with the settings object, and disagreeing would
        # present as a flag flipped in Terraform that changes nothing, with no
        # error anywhere to say why.
        #
        # The tables both exist already: `terraform/identity.tf` created all
        # four of M5's and M6's in the apply that landed M6, deliberately ahead
        # of the code that reads them, so this adoption is a backend change with
        # no apply in front of it.
        passkeys=DynamoPasskeyStore(repository(PASSKEYS)),
        webauthn_challenges=DynamoWebAuthnChallengeStore(
            repository(WEBAUTHN_CHALLENGES)
        ),
    )

    return build_identity_router(
        identity_settings,
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
        email_sender=build_email_sender(identity_settings),
        # M6's client secrets, as an argument rather than a settings field. See
        # `build_oauth_client_secrets` for why the package draws that line and
        # why an empty mapping is the honest thing to pass when nothing is
        # configured.
        oauth_client_secrets=build_oauth_client_secrets(settings),
    )


#: The keys of the `webbpulse-<env>/app` secret that carry the OAuth client
#: secrets, mapped to the provider names the package knows.
#:
#: The provider names are the package's, `IdentitySettings.oauth_providers` is a
#: `Literal["google", "github"]`, and `OAuthService` looks the secret up by that
#: name. The key names are this product's, because the secret is this product's.
#: Keeping the mapping here as one dict rather than two string literals inside
#: the function is what makes adding a provider one line, on the day the package
#: gains one.
OAUTH_SECRET_KEYS = {
    "google": "oauth_google_client_secret",
    "github": "oauth_github_client_secret",
}


def build_oauth_client_secrets(settings: Settings) -> dict[str, str]:
    """The M6 OAuth client secrets, from the single app secret. Possibly empty.

    ## Why this is an argument and not a setting

    `build_identity_router` takes `oauth_client_secrets` as a keyword argument
    rather than reading it off `IdentitySettings`, and the package's own
    docstring gives the reason: a secret that is a settings field is a secret
    that appears in a `repr`, in a pydantic validation error, and in whatever
    log line prints the settings object. So the two client ids travel as
    `IDENTITY_*` environment variables and are ordinary fields, and the two
    secrets travel through here and are on no object that anything renders.

    They are also deliberately not Lambda environment variables. Memory's rule
    for this estate is one JSON secret per service per environment, reached
    through `APP_SECRETS_ARN`, and a client secret in a function's environment
    is a secret visible in the console, in `get-function-configuration` and in
    every Terraform plan that touches the function.

    ## Why every key is optional and an empty result is a success

    **Returning `{}` is the ordinary state today, not a failure.** No OAuth app
    has been registered, so neither key is in the secret and neither client id
    is set. With no client id the package's `enabled_providers()` is empty and
    `build_identity_router` declares no OAuth route at all, so there is no route
    that could want a secret. Raising here for a missing key would turn a
    deployment that is correctly serving no OAuth into a cold start failure.

    That stays true one provider at a time. Registering Google alone puts
    `oauth_google_client_secret` in the secret and leaves `github` out of this
    mapping, and the package mounts the routes with only Google enabled.

    A client id set with no matching secret is the one bad combination this
    cannot prevent, and it does not try to: the routes mount, the start route
    works, and the token exchange answers 503 with a message that names no
    configuration. That is the package's behaviour and it is the right one,
    because the alternative is a service that will not start over a key that
    only one route needs.

    ## Why it does not go through `Settings.__getattribute__`

    `Settings` resolves exactly four secret fields lazily by name, listed in
    `SECRET_FIELDS`, and adding these two there would make them settings fields,
    which is precisely what the package's design is avoiding. `load_app_secrets`
    returns the whole flat map and caches it per execution environment, so
    reading two more keys off it costs no extra Secrets Manager call: by the
    time the identity function serves a request it has already fetched the blob
    for `SECRET_KEY`.

    Called once at composition time rather than per request, so a rotated secret
    is picked up on the next cold start, which is the same contract every other
    value from this secret has.
    """
    arn = settings.APP_SECRETS_ARN or settings.app_secrets_arn
    if not arn:
        # A local run or a test with no secret configured. Nothing to read, and
        # no OAuth route will be declared anyway without a client id.
        return {}

    from app.secrets import load_app_secrets

    loaded = load_app_secrets(arn)
    return {
        provider: loaded[key]
        for provider, key in OAUTH_SECRET_KEYS.items()
        if loaded.get(key)
    }


def build_email_sender(identity_settings: Any) -> Any:
    """The `EmailSender` for the four M3 routes, or `None` when SES is absent.

    Returning `None` is a supported state rather than a failure, and it is the
    reason this is a function rather than two lines above. `IDENTITY_EMAIL_FROM`
    is set by `terraform/lambda_domains.tf` only where SES exists, which is
    where `local.custom_domains_enabled` is true, and a staging profile without
    custom domains has no hosted zone to verify a sending domain in. The package
    then mounts the four routes only when a sender is supplied, so such a
    deployment serves the M1 documents and the six M2 flows and declares no
    route it cannot honour. `terraform/ses.tf` has the full reasoning.

    Constructing the client here rather than at import, for the reason the
    module docstring gives about the KMS client: nothing in this package calls
    AWS at import time, and a `boto3.client` at module scope is a credential
    resolution in every test that transitively imports this.

    `from_settings` rather than a keyword list, so the from address and the
    configuration set travel from the environment through `IdentitySettings` on
    one path. `ses_configuration_set` unset means the key is omitted from the
    `SendEmail` call rather than sent empty, which matters: a configuration set
    that does not exist is a hard failure on every send, and an empty string is
    a name that does not exist rather than an absence.
    """
    if not identity_settings.email_from:
        return None

    import boto3
    from webbpulse.identity.email import SesV2EmailSender

    return SesV2EmailSender.from_settings(identity_settings, boto3.client("sesv2"))
