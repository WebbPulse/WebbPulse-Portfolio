"""Portfolio's settings, on top of the shared package's base.

Nothing here is a secret, so constructing this reads no AWS and importing needs none.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator, model_validator
from webbpulse.config import BaseServiceSettings

LOCALHOST_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:4000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:4000",
    "http://127.0.0.1:5173",
]

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,http://localhost:5173,http://localhost:4000,https://portfolio.webbpulse.com"
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
    """Portfolio's settings. Constructing this reads no AWS."""

    ENVIRONMENT: str = "development"
    DYNAMODB_TABLE_PREFIX: str = "webbpulse-development"
    DYNAMODB_ENDPOINT_URL: Optional[str] = None

    APP_NAME: str = "Portfolio Blog API"
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, built on first use rather than at import."""
    return Settings()


def reset_settings_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    get_settings.cache_clear()


settings = get_settings()
