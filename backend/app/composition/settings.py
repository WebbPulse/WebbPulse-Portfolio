"""Portfolio's settings, on top of the shared package's base.

`BaseServiceSettings` carries the five fields every WebbPulse service has:
`environment`, `service_name`, `log_level`, `app_secrets_arn` and the two CORS
fields. Everything below them is Portfolio's own.

**The change PR 4 makes is where a missing secret fails.** The class this
replaces ended in a `model_validator(mode="after")` that raised when
`SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` or `ADMIN_EMAIL` was still
unset, and the module ended in a bare `settings = Settings()`. Together those
made importing anything under `app/` fail without secrets, which is exactly what
the `public` domain must not do: it is the one function with no Secrets Manager
access at all, and an import-time read would fail it on every cold start with no
route ever reached.

So the four secrets are ordinary optional fields here. They are filled from the
`APP_SECRETS_ARN` JSON secret on first read rather than at construction, by
`_resolve_secret`, and a domain that genuinely needs one calls
`require_secrets()` and gets the same fail-fast message the validator used to
raise, at request time instead of at import time.

Uppercase field names are kept deliberately. `BaseServiceSettings` is
case-insensitive, so `ENVIRONMENT` and `environment` are the same variable and
the environment variable names Terraform sets do not change; keeping the
attribute spelling means the ~40 `settings.DYNAMODB_TABLE_PREFIX` call sites
across the application do not change either, which keeps this PR's diff about
composition rather than about renaming.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator, model_validator
from webbpulse.config import BaseServiceSettings

# Settings filled from the single JSON secret named by APP_SECRETS_ARN. Its
# keys are these names exactly, so there is no mapping to keep in step.
SECRET_FIELDS = ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL")

LOCALHOST_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:4000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:4000",
    "http://127.0.0.1:5173",
]

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,http://localhost:5173,http://localhost:4000,"
    "https://webbpulse.com,https://www.webbpulse.com,http://webbpulse.com"
)

# How Portfolio's free-text `ENVIRONMENT` maps onto the base class's
# `environment`, which is a Literal of local/test/staging/production. Anything
# unrecognised lands on "local", which is the safe end: it is the value that
# grants the least, and `is_production` stays False for it.
ENVIRONMENT_ALIASES = {
    "development": "local",
    "dev": "local",
    "local": "local",
    "test": "test",
    "testing": "test",
    "staging": "staging",
    "production": "production",
    "prod": "production",
}


class Settings(BaseServiceSettings):
    """Portfolio's settings. Constructing this reads no AWS and no secret."""

    ENVIRONMENT: str = "development"
    DYNAMODB_TABLE_PREFIX: str = "webbpulse-development"
    DYNAMODB_ENDPOINT_URL: Optional[str] = None
    APP_SECRETS_ARN: Optional[str] = None

    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_EMAIL: Optional[str] = None

    LOGIN_MAX_FAILURES: int = 10
    LOGIN_FAILURE_WINDOW_SECONDS: int = 900

    # M1's issuer, and the only `IDENTITY_*` variable this class reads for it.
    #
    # The rest of M1's configuration is not here on purpose. `IdentitySettings`
    # in `webbpulse.identity` is a `BaseSettings` with `env_prefix="IDENTITY_"`,
    # so it reads `IDENTITY_AUDIENCE`, `IDENTITY_SIGNING_KEY_ARNS` and the other
    # dozen fields out of the environment itself. Restating them here would be a
    # second copy of the same list, kept in step by hand, with this one's types
    # and validation necessarily weaker than the package's.
    #
    # This one field is the exception because the composition root needs a cheap
    # way to answer "is the identity application configured at all" before it
    # constructs `IdentitySettings`, which raises when it is not. `IDENTITY_ISSUER`
    # is required by that class and set by Terraform on every deployed identity
    # function, so its presence is exactly that question. Naming it here rather
    # than reading `os.environ` in the composition root keeps every environment
    # variable this application reads visible in one class.
    IDENTITY_ISSUER: Optional[str] = None

    APP_NAME: str = "Portfolio Blog API"
    SITE_URL: str = "https://www.webbpulse.com"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # The two `POWERTOOLS_*` settings are gone with the dependency. Every domain
    # service now logs through `app/core/logging.py`, which is
    # `webbpulse.logging`, and the entrypoints already passed `service_name` and
    # `environment` to `configure_logging` rather than reading either of them.
    # Terraform never set them on a domain function, so nothing deployed loses a
    # variable it was reading.
    CORS_ORIGINS: str = DEFAULT_CORS_ORIGINS

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            return sorted(set(origins + LOCALHOST_ORIGINS))
        return value

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalise_app_log_level(cls, value: Any) -> Any:
        """Accept `info` as well as `INFO`, like the base class's `log_level`."""
        return value.strip().upper() if isinstance(value, str) else value

    # `BaseServiceSettings` names its own fields in lower case, and the shared
    # package reads those: `create_app` takes `cors_allow_origins` and
    # `cors_allow_credentials` off the settings object. A pydantic field cannot
    # be shadowed by a property, so the two spellings are reconciled after
    # validation instead: Portfolio's uppercase names stay the ones the
    # application and Terraform use, and the lower case ones are derived.
    #
    # `environment` is the one that needs care, and it has to be translated
    # *before* validation rather than after. `BaseServiceSettings` is
    # case-insensitive, so the base's `environment` and Portfolio's
    # `ENVIRONMENT` are fed by the same `ENVIRONMENT` environment variable.
    # That means the base's Literal runs against Portfolio's raw value: with
    # `ENVIRONMENT=development` set, which is both the documented default and
    # what a developer actually exports, the model raised
    #
    #     Input should be 'local', 'test', 'staging' or 'production'
    #
    # and never reached the `mode="after"` validator that was supposed to do
    # the mapping. `ENVIRONMENT=dev` failed the same way. Only leaving the
    # variable unset worked, because then the base fell back to its own
    # "local" default and the field was never given Portfolio's spelling.
    #
    # Mapping in a `mode="before"` model validator fixes that: the raw input
    # is rewritten so `environment` already holds a Literal member by the time
    # the field is validated, while `ENVIRONMENT` keeps the free-text value
    # the application and Terraform use.
    @model_validator(mode="before")
    @classmethod
    def _map_environment_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Case-insensitively, since the environment variable may arrive under
        # any spelling and pydantic-settings matches without regard to case.
        keys = [key for key in data if key.lower() == "environment"]
        if not keys:
            return data
        raw = data[keys[0]]
        if not isinstance(raw, str):
            return data

        mapped = ENVIRONMENT_ALIASES.get(raw.strip().lower(), "local")
        data = dict(data)
        # Portfolio's own field keeps the value as given; the base's Literal
        # field gets the translation. Both are written explicitly because a
        # single case-insensitive key would otherwise feed both.
        for key in keys:
            data.pop(key)
        data["ENVIRONMENT"] = raw
        data["environment"] = mapped
        return data

    @model_validator(mode="after")
    def _mirror_base_fields(self) -> "Settings":
        object.__setattr__(
            self,
            "environment",
            ENVIRONMENT_ALIASES.get(self.ENVIRONMENT.strip().lower(), "local"),
        )
        object.__setattr__(self, "log_level", self.LOG_LEVEL)
        origins = self.CORS_ORIGINS
        object.__setattr__(
            self,
            "cors_allow_origins",
            list(origins) if isinstance(origins, list) else [origins],
        )
        return self

    def _resolve_secret(self, field: str) -> Optional[str]:
        """One secret field, from the environment first and the blob second.

        Reading a field that is already set costs nothing. Reading one that is
        not, with an ARN configured, fetches the blob once per execution
        environment and fills every field it carries, so four unset fields cost
        one Secrets Manager call rather than four.

        The fetch itself is `webbpulse.config.load_json_secret`, reached through
        `app.secrets`, so the caching and the "this secret is not a JSON object"
        errors are the shared package's rather than a second copy of them here.
        """
        current = object.__getattribute__(self, field)
        if current is not None:
            return current
        arn = self.APP_SECRETS_ARN or self.app_secrets_arn
        if not arn:
            return None

        from app.secrets import load_app_secrets

        loaded = load_app_secrets(arn)
        for name in SECRET_FIELDS:
            if object.__getattribute__(self, name) is None:
                value = loaded.get(name)
                if value is not None:
                    object.__setattr__(self, name, value)
        return object.__getattribute__(self, field)

    def __getattribute__(self, name: str) -> Any:
        # Only the four secrets are lazy; every other attribute takes the
        # ordinary path, so this costs one set membership test per access.
        if name in SECRET_FIELDS:
            return object.__getattribute__(self, "_resolve_secret")(name)
        return object.__getattribute__(self, name)

    def require_secrets(self, *fields: str) -> None:
        """Assert the named secrets are readable, or raise saying which are not.

        This is the failure the old `resolve_secrets` validator produced, moved
        from import time to the point of use. A domain that needs the signing
        key calls it; `public`, which needs none of them, never does and so runs
        with no Secrets Manager permission at all.
        """
        wanted = fields or SECRET_FIELDS
        missing = [field for field in wanted if getattr(self, field) is None]
        if missing:
            raise ValueError(
                "Missing required settings (set them as environment variables or "
                f"as keys of the APP_SECRETS_ARN secret): {', '.join(missing)}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, built on first use rather than at import.

    Behind a cache on purpose: a missing environment variable then fails the
    request that needed it rather than the whole cold start, which is the
    difference between one bad response and a function that cannot start.
    """
    return Settings()


def reset_settings_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    get_settings.cache_clear()


settings = get_settings()
