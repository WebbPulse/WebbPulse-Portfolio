import boto3
import pytest
from pydantic import ValidationError

from app.config import Settings, load_ssm_parameters


def put_parameters(prefix, values):
    ssm = boto3.client("ssm", region_name="us-west-2")
    for name, value in values.items():
        ssm.put_parameter(
            Name=f"{prefix}/{name}", Value=value, Type="SecureString", Overwrite=True
        )


@pytest.fixture
def clear_secret_env(monkeypatch):
    for name in ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_secrets_resolve_from_ssm(clear_secret_env, monkeypatch):
    put_parameters(
        "/webbpulse/test",
        {
            "secret-key": "ssm-secret",
            "admin-username": "ssm-admin",
            "admin-password": "ssm-password",
            "admin-email": "ssm@example.com",
        },
    )
    monkeypatch.setenv("SSM_PARAMETER_PREFIX", "/webbpulse/test")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "ssm-secret"
    assert settings.ADMIN_USERNAME == "ssm-admin"
    assert settings.ADMIN_PASSWORD == "ssm-password"
    assert settings.ADMIN_EMAIL == "ssm@example.com"


@pytest.mark.unit
def test_environment_overrides_ssm(clear_secret_env, monkeypatch):
    put_parameters("/webbpulse/test", {"secret-key": "ssm-secret"})
    monkeypatch.setenv("SSM_PARAMETER_PREFIX", "/webbpulse/test")
    monkeypatch.setenv("SECRET_KEY", "env-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "env-admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "env-password")
    monkeypatch.setenv("ADMIN_EMAIL", "env@example.com")
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "env-secret"


@pytest.mark.unit
def test_missing_secrets_fail_fast(clear_secret_env, monkeypatch):
    monkeypatch.setenv("SSM_PARAMETER_PREFIX", "/webbpulse/empty")
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)
    message = str(excinfo.value)
    assert "SECRET_KEY" in message and "ADMIN_EMAIL" in message


@pytest.mark.unit
def test_missing_secrets_without_ssm_fail_fast(clear_secret_env, monkeypatch):
    monkeypatch.delenv("SSM_PARAMETER_PREFIX", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.unit
def test_load_ssm_parameters_returns_only_found():
    put_parameters("/webbpulse/partial", {"secret-key": "x"})
    found = load_ssm_parameters("/webbpulse/partial", ["secret-key", "admin-email"])
    assert found == {"secret-key": "x"}


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
