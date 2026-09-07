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
def test_missing_keys_fail_when_required_not_when_constructed(
    clear_secret_env, monkeypatch
):
    """PR 4 moved this failure from construction to the point of use.

    The class this replaces raised here, at `Settings(...)`, which made
    importing anything under `app/` fail without secrets. That is what the
    `public` function must not do: it holds no Secrets Manager permission at
    all, so an import-time read would fail every cold start before a single
    route was reached. The message is unchanged and still names every unset
    field, it is just raised by `require_secrets` instead.
    """
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
def test_require_secrets_passes_when_the_named_fields_resolve(
    clear_secret_env, monkeypatch
):
    """A domain names only the secrets it needs, and a partial blob suffices.

    `resume` and `content` need the signing key and nothing else, so a secret
    carrying only `SECRET_KEY` has to satisfy them. Requiring all four would
    put the admin credentials in the read path of two functions that never
    authenticate anyone.
    """
    arn = create_app_secret("webbpulse-partial-require/app", {"SECRET_KEY": "sm"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    settings = Settings(_env_file=None)
    settings.require_secrets("SECRET_KEY")


@pytest.mark.unit
def test_unreadable_secret_raises_rather_than_reporting_missing(
    clear_secret_env, monkeypatch
):
    """An ARN pointing at a secret that is not there is a misconfiguration and
    must surface as itself, not as a vague 'missing setting'.

    It now surfaces on the first read of a secret field rather than at
    construction, because that is where the blob is fetched. The distinction
    that matters is unchanged: a bad ARN raises the boto3 error, so it reads as
    the misconfiguration it is instead of as four fields that happen to be
    unset.
    """
    monkeypatch.setenv("APP_SECRETS_ARN", MISSING_SECRET_ARN)
    settings = Settings(_env_file=None)
    with pytest.raises(Exception) as excinfo:
        settings.SECRET_KEY
    raised = f"{type(excinfo.value).__name__} {excinfo.value}"
    assert "ResourceNotFound" in raised


@pytest.mark.unit
def test_settings_construct_with_no_arn_and_no_environment(
    clear_secret_env, monkeypatch
):
    """The property every domain image's cold start depends on.

    With no `APP_SECRETS_ARN` and no secret in the environment, constructing
    settings must succeed and reading a secret must return `None` rather than
    calling AWS. `tests/entrypoints/test_entrypoint_isolation.py` asserts the
    same thing end to end, by building each application under `env -i`.
    """
    monkeypatch.delenv("APP_SECRETS_ARN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY is None
    assert settings.ADMIN_USERNAME is None

    with pytest.raises(ValueError) as excinfo:
        settings.require_secrets("SECRET_KEY")
    assert "SECRET_KEY" in str(excinfo.value)


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
