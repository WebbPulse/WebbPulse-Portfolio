"""Portfolio's settings, on top of the shared package's base.

The four secret fields are optional and resolved from the `APP_SECRETS_ARN`
blob on first read, so constructing this reads no AWS and importing needs none.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator, model_validator
from webbpulse.config import BaseServiceSettings

SECRET_FIELDS = ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL")
"""Settings filled from the single JSON secret named by APP_SECRETS_ARN, whose keys
are these names exactly."""

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
"""Maps Portfolio's free-text `ENVIRONMENT` onto the base class's Literal. Anything
unrecognised lands on "local", the value that grants the least."""


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

    IDENTITY_ISSUER: Optional[str] = None
    """The identity issuer. Present exactly when the identity application is
    configured, which is how the composition root tests for it cheaply. Every other
    `IDENTITY_*` field belongs to `IdentitySettings`."""

    APP_NAME: str = "Portfolio Blog API"
    SITE_URL: str = "https://www.webbpulse.com"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = DEFAULT_CORS_ORIGINS

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Split a comma separated origin list and add the localhost origins."""
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            return sorted(set(origins + LOCALHOST_ORIGINS))
        return value

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalise_app_log_level(cls, value: Any) -> Any:
        """Accept `info` as well as `INFO`, like the base class's `log_level`."""
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="before")
    @classmethod
    def _map_environment_alias(cls, data: Any) -> Any:
        """Translate the raw `ENVIRONMENT` before the base's Literal validates it.

        Both fields are fed by the same case-insensitive variable, so the base
        would otherwise reject Portfolio's free-text spellings.
        """
        if not isinstance(data, dict):
            return data
        keys = [key for key in data if key.lower() == "environment"]
        if not keys:
            return data
        raw = data[keys[0]]
        if not isinstance(raw, str):
            return data

        mapped = ENVIRONMENT_ALIASES.get(raw.strip().lower(), "local")
        data = dict(data)
        for key in keys:
            data.pop(key)
        data["ENVIRONMENT"] = raw
        data["environment"] = mapped
        return data

    @model_validator(mode="after")
    def _mirror_base_fields(self) -> "Settings":
        """Derive the base class's lower case fields from Portfolio's own."""
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

        One fetch fills every unset field it carries, so several unset fields
        still cost a single Secrets Manager call.
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
        """Resolve the secret fields lazily; everything else takes the fast path."""
        if name in SECRET_FIELDS:
            return object.__getattribute__(self, "_resolve_secret")(name)
        return object.__getattribute__(self, name)

    def require_secrets(self, *fields: str) -> None:
        """Assert the named secrets are readable, or raise saying which are not.

        A domain that needs none never calls this, so it needs no Secrets
        Manager permission at all.
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
    """The process-wide settings, built on first use rather than at import."""
    return Settings()


def reset_settings_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    get_settings.cache_clear()


settings = get_settings()
