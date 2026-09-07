import boto3
import pytest
from pydantic import ValidationError

from app import secrets as app_secrets
from app.config import Settings


def create_secrets(prefix, values):
    client = boto3.client("secretsmanager", region_name="us-west-2")
    for name, value in values.items():
        client.create_secret(Name=f"{prefix}/{name}", SecretString=value)


def create_secret_without_value(prefix, name):
    client = boto3.client("secretsmanager", region_name="us-west-2")
    client.create_secret(Name=f"{prefix}/{name}")


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
    create_secrets(
        "webbpulse/test",
        {
            "secret-key": "sm-secret",
            "admin-username": "sm-admin",
            "admin-password": "sm-password",
            "admin-email": "sm@example.com",
        },
    )
    monkeypatch.setenv("SECRETS_PREFIX", "webbpulse/test")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "sm-secret"
    assert settings.ADMIN_USERNAME == "sm-admin"
    assert settings.ADMIN_PASSWORD == "sm-password"
    assert settings.ADMIN_EMAIL == "sm@example.com"


@pytest.mark.unit
def test_environment_overrides_secrets_manager(clear_secret_env, monkeypatch):
    create_secrets("webbpulse/override", {"secret-key": "sm-secret"})
    monkeypatch.setenv("SECRETS_PREFIX", "webbpulse/override")
    monkeypatch.setenv("SECRET_KEY", "env-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "env-password")
    monkeypatch.setenv("ADMIN_EMAIL", "env@example.com")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "env-secret"


@pytest.mark.unit
def test_missing_secrets_fail_fast(clear_secret_env, monkeypatch):
    """Secrets that exist but have no value yet fail as missing settings, with
    every unset field named."""
    for key in ("secret-key", "admin-username", "admin-password", "admin-email"):
        create_secret_without_value("webbpulse/empty", key)
    monkeypatch.setenv("SECRETS_PREFIX", "webbpulse/empty")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "SECRET_KEY" in message and "ADMIN_EMAIL" in message


@pytest.mark.unit
def test_wrong_prefix_raises_rather_than_reporting_missing(
    clear_secret_env, monkeypatch
):
    """A prefix pointing at secrets that do not exist is a misconfiguration and
    must surface as itself, not as a vague 'missing setting'."""
    monkeypatch.setenv("SECRETS_PREFIX", "webbpulse/nonexistent")
    with pytest.raises(Exception) as excinfo:
        Settings(_env_file=None)
    raised = f"{type(excinfo.value).__name__} {excinfo.value}"
    assert "ResourceNotFound" in raised


@pytest.mark.unit
def test_missing_secrets_without_prefix_fail_fast(clear_secret_env, monkeypatch):
    monkeypatch.delenv("SECRETS_PREFIX", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.unit
def test_load_secrets_skips_a_secret_with_no_value():
    """A secret that exists but is not yet populated is skipped, so the caller
    can report that field as missing. Unlike SSM get_parameters, Secrets
    Manager has no partial response, so this is the only 'not found' that is
    tolerated."""
    create_secrets("webbpulse/partial", {"secret-key": "x"})
    create_secret_without_value("webbpulse/partial", "admin-email")
    found = app_secrets.load_secrets("webbpulse/partial", ["secret-key", "admin-email"])
    assert found == {"secret-key": "x"}


@pytest.mark.unit
def test_secret_without_a_version_reads_as_absent():
    """Between the apply that creates a secret and the copy that fills it, the
    secret exists with no version. That reads as absent, not as an error."""
    create_secret_without_value("webbpulse/novalue", "admin-email")
    found = app_secrets.load_secrets("webbpulse/novalue", ["admin-email"])
    assert found == {}


@pytest.mark.unit
def test_nonexistent_secret_raises():
    """A secret that is not there at all must not be swallowed into a confusing
    'missing setting' error."""
    with pytest.raises(Exception):
        app_secrets.load_secret("webbpulse/does-not-exist/secret-key")


@pytest.mark.unit
def test_values_are_cached_per_execution_environment():
    create_secrets("webbpulse/cached", {"secret-key": "first"})
    name = app_secrets.secret_name("webbpulse/cached", "secret-key")
    assert app_secrets.load_secret(name) == "first"

    boto3.client("secretsmanager", region_name="us-west-2").put_secret_value(
        SecretId=name, SecretString="second"
    )
    # Still the cached value: a warm invocation makes no further call.
    assert app_secrets.load_secret(name) == "first"

    app_secrets.reset_cache()
    assert app_secrets.load_secret(name) == "second"


@pytest.mark.unit
def test_secret_name_joins_prefix_and_key():
    assert app_secrets.secret_name("webbpulse-staging", "secret-key") == (
        "webbpulse-staging/secret-key"
    )
    assert app_secrets.secret_name("webbpulse-staging/", "secret-key") == (
        "webbpulse-staging/secret-key"
    )


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
