"""Settings resolution: Secrets Manager, environment overrides and aliases."""

import json

import boto3
import pytest

from app import secrets as app_secrets
from app.config import Settings

FULL_PAYLOAD = {
    "SECRET_KEY": "sm-secret",
    "ADMIN_USERNAME": "sm-admin",
    "ADMIN_PASSWORD": "sm-password",
    "ADMIN_EMAIL": "sm@example.com",
}

MISSING_SECRET_ARN = "arn:aws:secretsmanager:us-west-2:123456789012:secret:webbpulse-test/missing-AbCdEf"


def create_app_secret(name, payload):
    """Create the single JSON secret and return its ARN."""
    client = boto3.client("secretsmanager", region_name="us-west-2")
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return client.create_secret(Name=name, SecretString=body)["ARN"]


@pytest.fixture(autouse=True)
def clear_secrets_cache():
    """The reader caches per execution environment; each test starts empty."""
    app_secrets.reset_cache()
    yield
    app_secrets.reset_cache()


@pytest.fixture
def clear_secret_env(monkeypatch):
    """Remove the secret-backed settings from the environment."""
    for name in ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_secrets_resolve_from_secrets_manager(clear_secret_env, monkeypatch):
    """With an ARN set and no environment, the settings come from the secret."""
    arn = create_app_secret("webbpulse-test/app", FULL_PAYLOAD)
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "sm-secret"
    assert settings.ADMIN_USERNAME == "sm-admin"
    assert settings.ADMIN_PASSWORD == "sm-password"
    assert settings.ADMIN_EMAIL == "sm@example.com"


@pytest.mark.unit
def test_environment_overrides_secrets_manager(clear_secret_env, monkeypatch):
    """An environment variable wins over the same key in the secret."""
    arn = create_app_secret("webbpulse-override/app", FULL_PAYLOAD)
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    monkeypatch.setenv("SECRET_KEY", "env-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "env-password")
    monkeypatch.setenv("ADMIN_EMAIL", "env@example.com")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "env-secret"


@pytest.mark.unit
def test_environment_fills_only_the_keys_the_secret_omits(clear_secret_env, monkeypatch):
    """Env wins per field, so a blob that carries only some keys is topped up
    from the environment rather than being all-or-nothing."""
    arn = create_app_secret("webbpulse-partial/app", {"SECRET_KEY": "sm-secret"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    monkeypatch.setenv("ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "env-password")
    monkeypatch.setenv("ADMIN_EMAIL", "env@example.com")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "sm-secret"
    assert settings.ADMIN_USERNAME == "env-admin"


@pytest.mark.unit
def test_missing_keys_fail_when_required_not_when_constructed(clear_secret_env, monkeypatch):
    """PR 4 moved this failure from construction to the point of use."""
    arn = create_app_secret("webbpulse-empty/app", {"SECRET_KEY": "sm-secret"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)

    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "sm-secret"

    with pytest.raises(ValueError) as excinfo:
        settings.require_secrets()
    message = str(excinfo.value)
    assert "ADMIN_USERNAME" in message and "ADMIN_EMAIL" in message
    assert "SECRET_KEY" not in message


@pytest.mark.unit
def test_require_secrets_passes_when_the_named_fields_resolve(clear_secret_env, monkeypatch):
    """A domain names only the secrets it needs, and a partial blob suffices."""
    arn = create_app_secret("webbpulse-partial-require/app", {"SECRET_KEY": "sm"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    settings = Settings(_env_file=None)
    settings.require_secrets("SECRET_KEY")


@pytest.mark.unit
def test_unreadable_secret_raises_rather_than_reporting_missing(clear_secret_env, monkeypatch):
    """An ARN pointing at a secret that is not there is a misconfiguration and must
    surface as itself, not as a vague 'missing setting'.
    """
    monkeypatch.setenv("APP_SECRETS_ARN", MISSING_SECRET_ARN)
    settings = Settings(_env_file=None)
    with pytest.raises(Exception) as excinfo:
        settings.SECRET_KEY
    raised = f"{type(excinfo.value).__name__} {excinfo.value}"
    assert "ResourceNotFound" in raised


@pytest.mark.unit
def test_settings_construct_with_no_arn_and_no_environment(clear_secret_env, monkeypatch):
    """The property every domain image's cold start depends on."""
    monkeypatch.delenv("APP_SECRETS_ARN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY is None
    assert settings.ADMIN_USERNAME is None

    with pytest.raises(ValueError) as excinfo:
        settings.require_secrets("SECRET_KEY")
    assert "SECRET_KEY" in str(excinfo.value)


@pytest.mark.unit
def test_non_object_payload_is_rejected():
    """A payload that is not a JSON object is rejected."""
    arn = create_app_secret("webbpulse-list/app", json.dumps(["not", "a", "dict"]))
    with pytest.raises(ValueError):
        app_secrets.load_app_secrets(arn)


@pytest.mark.unit
def test_invalid_json_payload_is_rejected():
    """A payload that is not JSON at all is rejected."""
    arn = create_app_secret("webbpulse-garbage/app", "not json at all")
    with pytest.raises(ValueError):
        app_secrets.load_app_secrets(arn)


@pytest.mark.unit
def test_non_string_values_are_json_encoded_and_nulls_dropped():
    """Non-string values are JSON encoded and null values are dropped."""
    arn = create_app_secret(
        "webbpulse-types/app",
        {"SECRET_KEY": "x", "ADMIN_EMAIL": None, "RETRIES": 3},
    )
    assert app_secrets.load_app_secrets(arn) == {"SECRET_KEY": "x", "RETRIES": "3"}


@pytest.mark.unit
def test_values_are_cached_per_execution_environment():
    """A rotated secret is only seen after the cache is reset."""
    arn = create_app_secret("webbpulse-cached/app", {"SECRET_KEY": "first"})
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "first"

    boto3.client("secretsmanager", region_name="us-west-2").put_secret_value(
        SecretId=arn, SecretString=json.dumps({"SECRET_KEY": "second"})
    )
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "first"

    app_secrets.reset_cache()
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "second"


@pytest.mark.unit
def test_cors_origins_include_localhost(monkeypatch):
    """The configured origins are kept and localhost is always added."""
    monkeypatch.setenv("CORS_ORIGINS", "https://www.webbpulse.com, https://webbpulse.com")
    settings = Settings(_env_file=None)
    assert "https://www.webbpulse.com" in settings.CORS_ORIGINS
    assert "https://webbpulse.com" in settings.CORS_ORIGINS
    assert any(origin.startswith("http://localhost") for origin in settings.CORS_ORIGINS)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("development", "local"),
        ("dev", "local"),
        ("local", "local"),
        ("test", "test"),
        ("testing", "test"),
        ("staging", "staging"),
        ("production", "production"),
        ("prod", "production"),
    ],
)
def test_environment_aliases_map_to_the_base_literal(monkeypatch, raw, expected):
    """Each environment alias maps to its base literal, leaving the raw value intact."""
    monkeypatch.setenv("ENVIRONMENT", raw)
    settings = Settings(_env_file=None)
    assert settings.ENVIRONMENT == raw
    assert settings.environment == expected


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["DEVELOPMENT", "Dev", "  development  "])
def test_environment_aliases_ignore_case_and_surrounding_space(monkeypatch, raw):
    """Alias matching ignores case and surrounding whitespace."""
    monkeypatch.setenv("ENVIRONMENT", raw)
    assert Settings(_env_file=None).environment == "local"


@pytest.mark.unit
def test_unrecognised_environment_falls_back_to_local(monkeypatch):
    """An unknown value lands on "local" rather than failing validation."""
    monkeypatch.setenv("ENVIRONMENT", "whatever")
    settings = Settings(_env_file=None)
    assert settings.ENVIRONMENT == "whatever"
    assert settings.environment == "local"
    assert settings.is_production is False


@pytest.mark.unit
def test_environment_defaults_to_development_when_unset(monkeypatch):
    """With no environment set the default is development, which maps to local."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.ENVIRONMENT == "development"
    assert settings.environment == "local"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "is_production"),
    [("production", True), ("prod", True), ("staging", False), ("development", False)],
)
def test_is_production_follows_the_mapped_environment(monkeypatch, raw, is_production):
    """is_production follows the mapped environment rather than the raw value."""
    monkeypatch.setenv("ENVIRONMENT", raw)
    assert Settings(_env_file=None).is_production is is_production
