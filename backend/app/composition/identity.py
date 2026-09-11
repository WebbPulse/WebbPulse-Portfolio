"""Builds the identity router, its settings, and the AWS clients they need.

The router mounts with no prefix of its own: the package places every route
under the issuer's path. Clients are constructed lazily so no import calls AWS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import APIRouter

    from .settings import Settings


def build_identity_settings(settings: Settings) -> Any:
    """`IdentitySettings` for this product, read from the `IDENTITY_*` environment.

    Raises `pydantic.ValidationError` at startup when that environment is
    incomplete or inconsistent, rather than on the first request affected.
    """
    from webbpulse.identity import IdentitySettings

    del settings
    return IdentitySettings()  # pyright: ignore[reportCallIssue]


def build_router(settings: Settings) -> APIRouter:
    """The identity router, mounted by the caller with no prefix of its own.

    Which route groups the package declares follows from which stores, senders
    and settings flags are supplied here; unsupplied halves stay unmounted.
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
        """A package repository for one of the identity tables.

        Prefix and endpoint are passed explicitly so this reads the same
        `Settings` as the rest of the backend, endpoint override included.
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
        totp_factors=DynamoTotpFactorStore(repository(TOTP_FACTORS)),
        recovery_codes=DynamoRecoveryCodeStore(repository(RECOVERY_CODES)),
        oauth_states=DynamoOAuthStateStore(repository(OAUTH_STATES)),
        oauth_links=DynamoOAuthLinkStore(repository(OAUTH_LINKS)),
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
        attempts=DynamoLoginAttemptStore(repository(LOGIN_ATTEMPTS)),
        email_sender=build_email_sender(identity_settings),
        oauth_client_secrets=build_oauth_client_secrets(settings),
    )


#: Provider name to the upper case key carrying its client secret in the
#: `webbpulse-<env>/app` secret. Lookups are exact, so the case is load-bearing.
OAUTH_SECRET_KEYS = {
    "google": "OAUTH_GOOGLE_CLIENT_SECRET",
    "github": "OAUTH_GITHUB_CLIENT_SECRET",
}


def build_oauth_client_secrets(settings: Settings) -> dict[str, str]:
    """The OAuth client secrets, read from the single app secret. Possibly empty.

    Passed as an argument rather than held as a settings field so no secret can
    reach a `repr` or a log line. Empty is a success, not a failure.
    """
    arn = settings.APP_SECRETS_ARN or settings.app_secrets_arn
    if not arn:
        return {}

    from app.secrets import load_app_secrets

    loaded = load_app_secrets(arn)
    return {
        provider: loaded[key]
        for provider, key in OAUTH_SECRET_KEYS.items()
        if loaded.get(key)
    }


def build_email_sender(identity_settings: Any) -> Any:
    """The `EmailSender` for the email routes, or `None` when SES is absent.

    `None` is supported: the package mounts those routes only when a sender is
    supplied, so a deployment without SES declares no route it cannot honour.
    """
    if not identity_settings.email_from:
        return None

    import boto3
    from webbpulse.identity.email import SesV2EmailSender

    return SesV2EmailSender.from_settings(identity_settings, boto3.client("sesv2"))
