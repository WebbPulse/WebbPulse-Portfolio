"""Settings resolution: environment overrides and aliases."""

import pytest

from app.common.config import Settings


@pytest.mark.unit
def test_cors_origins_include_localhost(monkeypatch):
    """The configured origins are kept and localhost is always added."""
    monkeypatch.setenv("CORS_ORIGINS", "https://portfolio.webbpulse.com, https://staging.portfolio.webbpulse.com")
    settings = Settings(_env_file=None)
    assert "https://portfolio.webbpulse.com" in settings.CORS_ORIGINS
    assert "https://staging.portfolio.webbpulse.com" in settings.CORS_ORIGINS
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


@pytest.mark.unit
def test_settings_carry_no_secret_fields():
    """The public domain reads no secret, so the settings declare none."""
    fields = set(Settings.model_fields)
    assert not fields & {"SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL", "IDENTITY_ISSUER"}
