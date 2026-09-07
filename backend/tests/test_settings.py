import json

import boto3
import pytest
from pydantic import ValidationError

from app import secrets as app_secrets
from app.config import Settings

FULL_PAYLOAD = {
    "SECRET_KEY": "sm-secret",
    "ADMIN_USERNAME": "sm-admin",
    "ADMIN_PASSWORD": "sm-password",
    "ADMIN_EMAIL": "sm@example.com",
}

MISSING_SECRET_ARN = (
    "arn:aws:secretsmanager:us-west-2:123456789012:secret:webbpulse-test/missing-AbCdEf"
)


def create_app_secret(name, payload):
    """Create the single JSON secret and return its ARN.

    payload is written as-is when it is already a string, so a test can store a
    body that is not a JSON object.
    """
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
    for name in ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_secrets_resolve_from_secrets_manager(clear_secret_env, monkeypatch):
    arn = create_app_secret("webbpulse-test/app", FULL_PAYLOAD)
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "sm-secret"
    assert settings.ADMIN_USERNAME == "sm-admin"
    assert settings.ADMIN_PASSWORD == "sm-password"
    assert settings.ADMIN_EMAIL == "sm@example.com"


@pytest.mark.unit
def test_environment_overrides_secrets_manager(clear_secret_env, monkeypatch):
    arn = create_app_secret("webbpulse-override/app", FULL_PAYLOAD)
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    monkeypatch.setenv("SECRET_KEY", "env-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "env-password")
    monkeypatch.setenv("ADMIN_EMAIL", "env@example.com")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "env-secret"


@pytest.mark.unit
def test_environment_fills_only_the_keys_the_secret_omits(
    clear_secret_env, monkeypatch
):
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
def test_missing_keys_fail_fast(clear_secret_env, monkeypatch):
    """A blob missing keys fails as missing settings, with every unset field
    named."""
    arn = create_app_secret("webbpulse-empty/app", {"SECRET_KEY": "sm-secret"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "ADMIN_USERNAME" in message and "ADMIN_EMAIL" in message
    assert "SECRET_KEY" not in message


@pytest.mark.unit
def test_unreadable_secret_raises_rather_than_reporting_missing(
    clear_secret_env, monkeypatch
):
    """An ARN pointing at a secret that is not there is a misconfiguration and
    must surface as itself, not as a vague 'missing setting'."""
    monkeypatch.setenv("APP_SECRETS_ARN", MISSING_SECRET_ARN)
    with pytest.raises(Exception) as excinfo:
        Settings(_env_file=None)
    raised = f"{type(excinfo.value).__name__} {excinfo.value}"
    assert "ResourceNotFound" in raised


@pytest.mark.unit
def test_missing_secrets_without_arn_fail_fast(clear_secret_env, monkeypatch):
    monkeypatch.delenv("APP_SECRETS_ARN", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.unit
def test_non_object_payload_is_rejected():
    arn = create_app_secret("webbpulse-list/app", json.dumps(["not", "a", "dict"]))
    with pytest.raises(ValueError):
        app_secrets.load_app_secrets(arn)


@pytest.mark.unit
def test_invalid_json_payload_is_rejected():
    arn = create_app_secret("webbpulse-garbage/app", "not json at all")
    with pytest.raises(ValueError):
        app_secrets.load_app_secrets(arn)


@pytest.mark.unit
def test_non_string_values_are_json_encoded_and_nulls_dropped():
    arn = create_app_secret(
        "webbpulse-types/app",
        {"SECRET_KEY": "x", "ADMIN_EMAIL": None, "RETRIES": 3},
    )
    assert app_secrets.load_app_secrets(arn) == {"SECRET_KEY": "x", "RETRIES": "3"}


@pytest.mark.unit
def test_values_are_cached_per_execution_environment():
    arn = create_app_secret("webbpulse-cached/app", {"SECRET_KEY": "first"})
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "first"

    boto3.client("secretsmanager", region_name="us-west-2").put_secret_value(
        SecretId=arn, SecretString=json.dumps({"SECRET_KEY": "second"})
    )
    # Still the cached value: a warm invocation makes no further call.
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "first"

    app_secrets.reset_cache()
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "second"


@pytest.mark.unit
def test_cors_origins_include_localhost(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS", "https://www.webbpulse.com, https://webbpulse.com"
    )
    settings = Settings(_env_file=None)
    assert "https://www.webbpulse.com" in settings.CORS_ORIGINS
    assert "https://webbpulse.com" in settings.CORS_ORIGINS
    assert any(
        origin.startswith("http://localhost") for origin in settings.CORS_ORIGINS
    )
