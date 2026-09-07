from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.secrets import load_app_secrets

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


class Settings(BaseSettings):
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

    APP_NAME: str = "Portfolio Blog API"
    SITE_URL: str = "https://www.webbpulse.com"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    POWERTOOLS_SERVICE_NAME: str = "webbpulse-portfolio-api"
    POWERTOOLS_METRICS_NAMESPACE: str = "WebbPulse/Portfolio"
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,http://localhost:4000,"
        "https://webbpulse.com,https://www.webbpulse.com,http://webbpulse.com"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            return sorted(set(origins + LOCALHOST_ORIGINS))
        return value

    @model_validator(mode="after")
    def resolve_secrets(self):
        """Fill any secret not already set from the environment.

        An environment variable still wins, which keeps local development and
        the test suite free of AWS. Everything else is read from Secrets
        Manager once per execution environment and cached there.
        """
        missing = [field for field in SECRET_FIELDS if getattr(self, field) is None]
        if missing and self.APP_SECRETS_ARN:
            loaded = load_app_secrets(self.APP_SECRETS_ARN)
            for field in missing:
                value = loaded.get(field)
                if value is not None:
                    setattr(self, field, value)
            missing = [field for field in missing if getattr(self, field) is None]
        if missing:
            raise ValueError(
                "Missing required settings (set them as environment variables or "
                f"as keys of the APP_SECRETS_ARN secret): {', '.join(missing)}"
            )
        return self


settings = Settings()
