"""Where a missing secret fails, and which domains can miss one.

`tests/test_settings.py` covers the resolution itself: env first, blob second,
cached per execution environment. This module covers the two things around it
that the split actually rests on.

**Importing reads nothing.** A domain image's cold start imports `app` before it
has credentials, and `public` never has `secretsmanager:GetSecretValue` at all,
so an import that reached Secrets Manager would fail that function on every cold
start before a single route was reached. The subprocess tests here assert it the
only way it can be asserted, in a fresh interpreter with an empty environment,
because an import already performed by the suite proves nothing about a cold
one.

**A misconfigured function fails at startup, not on the unlucky request.**
Resolution being lazy is what makes the first property possible, but on its own
it moves the failure to whichever request first verifies a token, which reads as
an intermittent 500. `check_required_secrets` puts a single deliberate read at
startup for exactly the secrets the domains being served declare, so a bad ARN
is a cold start failure with a message naming the field.
"""

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import boto3
import pytest

from app import secrets as app_secrets
from app.composition.settings import Settings
from app.composition.wiring import DOMAINS, check_required_secrets

BACKEND = Path(__file__).resolve().parents[1]

MISSING_SECRET_ARN = (
    "arn:aws:secretsmanager:us-west-2:123456789012:secret:webbpulse-test/missing-AbCdEf"
)


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
    monkeypatch.delenv("APP_SECRETS_ARN", raising=False)


def create_app_secret(name, payload):
    client = boto3.client("secretsmanager", region_name="us-west-2")
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return client.create_secret(Name=name, SecretString=body)["ARN"]


def run_probe(source, env=None):
    """Run a snippet in a fresh interpreter with an empty environment.

    `env -i` is the point: the only variables set are the ones the interpreter
    itself needs. `PYTHONPATH` carries whatever makes `app` and the shared
    package importable in this checkout, which in CI is the installed
    distribution and locally is a path, so it is taken from the parent rather
    than hardcoded.
    """
    environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": os.pathsep.join(
            [str(BACKEND), *(p for p in sys.path if p and Path(p).is_dir())]
        ),
        # A `.pyc` write into a read-only tree is a hard failure, and the Lambda
        # filesystem is read-only outside `/tmp`.
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )


# --- Importing reads no secret ------------------------------------------------

IMPORT_PROBE = """
import json, sys
import app.config as config
from app.composition.settings import Settings

import webbpulse.config as shared_config
shared_config._secrets_client = lambda region=None: (
    (_ for _ in ()).throw(AssertionError("client built"))
)

app_module = __import__("app.entrypoints.%s", fromlist=["build_app"])
built = app_module.build_app()
print(json.dumps({"routes": len(built.routes), "arn": config.settings.APP_SECRETS_ARN}))
"""


@pytest.mark.unit
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_building_a_domain_app_makes_no_secrets_manager_call(domain):
    """The contract every domain image's cold start depends on.

    The ARN is set and points at a secret that is not there, so any call at all
    would raise. Building the application must still succeed: the failure moved
    to the first deliberate read, which is `check_required_secrets` in `main`.
    Run outside `mock_aws` on purpose, with no credentials, so a real call fails
    rather than being quietly served.
    """
    result = run_probe(
        IMPORT_PROBE % domain, env={"APP_SECRETS_ARN": MISSING_SECRET_ARN}
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["routes"] > 0
    assert payload["arn"] == MISSING_SECRET_ARN


@pytest.mark.unit
def test_importing_config_with_no_aws_environment_at_all():
    """No credentials, no region, no ARN: importing settings still works.

    This is what makes the route contract test able to import all four
    entrypoints, and what lets `public` run with no Secrets Manager grant.
    """
    result = run_probe(
        "from app.config import settings\n"
        "assert settings.SECRET_KEY is None\n"
        "assert settings.ADMIN_USERNAME is None\n"
        "print('ok')"
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


# --- Lazy resolution ----------------------------------------------------------


@pytest.mark.unit
def test_reading_a_secret_is_what_triggers_the_fetch(clear_secret_env, monkeypatch):
    """Constructing settings makes no call; the first read of a secret does."""
    calls = []
    arn = create_app_secret("webbpulse-lazy/app", {"SECRET_KEY": "sm-secret"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)

    real_load = app_secrets.load_app_secrets

    def counting_load(secret_arn, client=None):
        calls.append(secret_arn)
        return real_load(secret_arn, client)

    monkeypatch.setattr(app_secrets, "load_app_secrets", counting_load)

    settings = Settings(_env_file=None)
    assert calls == []

    assert settings.SECRET_KEY == "sm-secret"
    assert calls == [arn]


@pytest.mark.unit
def test_four_unset_fields_cost_one_fetch(clear_secret_env, monkeypatch):
    """One blob carries all four, so resolving them is one call, not four."""
    calls = []
    arn = create_app_secret(
        "webbpulse-onecall/app",
        {
            "SECRET_KEY": "k",
            "ADMIN_USERNAME": "u",
            "ADMIN_PASSWORD": "p",
            "ADMIN_EMAIL": "e@example.com",
        },
    )
    monkeypatch.setenv("APP_SECRETS_ARN", arn)

    real_load = app_secrets.load_app_secrets
    monkeypatch.setattr(
        app_secrets,
        "load_app_secrets",
        lambda a, client=None: (calls.append(a), real_load(a, client))[1],
    )

    settings = Settings(_env_file=None)
    assert settings.SECRET_KEY == "k"
    assert settings.ADMIN_USERNAME == "u"
    assert settings.ADMIN_PASSWORD == "p"
    assert settings.ADMIN_EMAIL == "e@example.com"
    assert calls == [arn]


@pytest.mark.unit
def test_env_var_short_circuits_the_fetch(clear_secret_env, monkeypatch):
    """An environment variable wins and no call is made at all.

    This is what keeps a local checkout and the suite free of AWS: the ARN here
    points at a secret that does not exist, so a fetch would raise.
    """
    monkeypatch.setenv("APP_SECRETS_ARN", MISSING_SECRET_ARN)
    monkeypatch.setenv("SECRET_KEY", "from-env")

    assert Settings(_env_file=None).SECRET_KEY == "from-env"


# --- require_secrets ----------------------------------------------------------


@pytest.mark.unit
def test_require_secrets_names_every_missing_field(clear_secret_env, monkeypatch):
    arn = create_app_secret("webbpulse-msg/app", {"SECRET_KEY": "k"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)

    with pytest.raises(ValueError) as excinfo:
        Settings(_env_file=None).require_secrets(
            "SECRET_KEY", "ADMIN_USERNAME", "ADMIN_EMAIL"
        )

    message = str(excinfo.value)
    assert "ADMIN_USERNAME" in message and "ADMIN_EMAIL" in message
    # The one that resolved is not reported as missing.
    assert "SECRET_KEY" not in message
    assert "APP_SECRETS_ARN" in message


@pytest.mark.unit
def test_cache_reset_makes_a_rotated_secret_visible():
    arn = create_app_secret("webbpulse-rotate/app", {"SECRET_KEY": "first"})
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "first"

    boto3.client("secretsmanager", region_name="us-west-2").put_secret_value(
        SecretId=arn, SecretString=json.dumps({"SECRET_KEY": "second"})
    )
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "first"

    app_secrets.reset_cache()
    assert app_secrets.load_app_secrets(arn)["SECRET_KEY"] == "second"


# --- check_required_secrets ---------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_a_deployed_environment_raises_on_a_missing_secret(
    clear_secret_env, monkeypatch, environment
):
    """The startup failure. Without it the first request that verifies a token
    is what discovers the misconfiguration, which reads as a random 500."""
    monkeypatch.setenv("ENVIRONMENT", environment)
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError, match="SECRET_KEY"):
        check_required_secrets([DOMAINS["resume"]], settings=settings)


@pytest.mark.unit
def test_a_local_environment_warns_rather_than_raising(clear_secret_env, monkeypatch):
    """A checkout with no AWS has to stay runnable."""
    monkeypatch.setenv("ENVIRONMENT", "local")
    settings = Settings(_env_file=None)

    with pytest.warns(UserWarning, match="SECRET_KEY"):
        check_required_secrets([DOMAINS["resume"]], settings=settings)


@pytest.mark.unit
@pytest.mark.parametrize("environment", ["staging", "production", "local"])
def test_public_never_asks_for_a_secret(clear_secret_env, monkeypatch, environment):
    """The least-privilege claim the whole split rests on.

    `public` declares no secret, so this must neither raise nor warn nor read,
    even in production with no secret available anywhere. If it ever did, the
    function would need a `secretsmanager:GetSecretValue` grant it does not have
    and would fail every cold start.
    """
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("APP_SECRETS_ARN", MISSING_SECRET_ARN)
    settings = Settings(_env_file=None)

    with warnings.catch_warnings():
        # Only ours. Promoting every warning would also catch a dependency's
        # unrelated DeprecationWarning, which says nothing about this code.
        warnings.simplefilter("error", UserWarning)
        check_required_secrets([DOMAINS["public"]], settings=settings)


@pytest.mark.unit
def test_a_deployed_environment_passes_when_the_secret_resolves(
    clear_secret_env, monkeypatch
):
    arn = create_app_secret("webbpulse-ok/app", {"SECRET_KEY": "sm-secret"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings(_env_file=None)

    with warnings.catch_warnings():
        # Only ours. Promoting every warning would also catch a dependency's
        # unrelated DeprecationWarning, which says nothing about this code.
        warnings.simplefilter("error", UserWarning)
        check_required_secrets([DOMAINS["resume"]], settings=settings)


@pytest.mark.unit
def test_identity_requires_the_admin_credentials_the_seed_reads(
    clear_secret_env, monkeypatch
):
    """`identity` owns `users` and seeds the admin from the blob, so the three
    admin fields are startup requirements for it and for nothing else."""
    arn = create_app_secret("webbpulse-identity/app", {"SECRET_KEY": "k"})
    monkeypatch.setenv("APP_SECRETS_ARN", arn)
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings(_env_file=None)

    with pytest.raises(ValueError) as excinfo:
        check_required_secrets([DOMAINS["identity"]], settings=settings)

    message = str(excinfo.value)
    for field in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL"):
        assert field in message


@pytest.mark.unit
@pytest.mark.parametrize(
    "domain,expected",
    [
        ("public", ()),
        ("content", ("SECRET_KEY",)),
        ("resume", ("SECRET_KEY",)),
        (
            "identity",
            ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_EMAIL"),
        ),
    ],
)
def test_the_declared_secrets_per_domain(domain, expected):
    """Pins the map Terraform's IAM grants are derived from.

    `content` and `resume` verify bearer tokens, so both need the signing key.
    `identity` also mints them and seeds the admin user. `public` does neither,
    which is why its function holds no `secretsmanager` action at all.
    """
    assert DOMAINS[domain].requires_secrets == expected


# --- Seeding is scoped to the domain that owns the table ----------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "domain,expected",
    [
        ("public", ()),
        ("resume", ()),
        ("content", ("site_content",)),
        ("identity", ("admin",)),
    ],
)
def test_a_domain_seeds_only_what_it_owns(domain, expected):
    """`content` used to run the admin seeder too.

    That made it write the `users` table `identity` owns and resolve the three
    admin secrets its descriptor says it does not need, so the descriptor and
    the runtime disagreed. Seeding is per-table now and the descriptor is the
    honest one.
    """
    assert DOMAINS[domain].seeds == expected


@pytest.mark.unit
def test_the_content_app_does_not_seed_the_admin_user(monkeypatch):
    """The behaviour, not just the descriptor.

    Asserted through a request against the built application, because the seed
    runs in middleware on the first request rather than at build time.
    """
    from starlette.testclient import TestClient

    from app.composition.wiring import build_domain_app

    seeded = []
    monkeypatch.setattr(
        "app.core.middleware.SEEDERS",
        {
            "admin": lambda: seeded.append("admin"),
            "site_content": lambda: seeded.append("site_content"),
        },
    )

    with TestClient(build_domain_app(DOMAINS["content"])) as client:
        client.get("/health")

    assert seeded == ["site_content"]


@pytest.mark.unit
def test_the_identity_app_still_seeds_the_admin_user(monkeypatch):
    """The admin seed on cold start has to keep working where it belongs."""
    from starlette.testclient import TestClient

    from app.composition.wiring import build_domain_app

    seeded = []
    monkeypatch.setattr(
        "app.core.middleware.SEEDERS",
        {
            "admin": lambda: seeded.append("admin"),
            "site_content": lambda: seeded.append("site_content"),
        },
    )

    with TestClient(build_domain_app(DOMAINS["identity"])) as client:
        client.get("/health")

    assert seeded == ["admin"]


@pytest.mark.unit
@pytest.mark.parametrize("domain", ["public", "resume"])
def test_a_domain_that_owns_no_table_runs_no_seeder(monkeypatch, domain):
    from starlette.testclient import TestClient

    from app.composition.wiring import build_domain_app

    seeded = []
    monkeypatch.setattr(
        "app.core.middleware.SEEDERS",
        {
            "admin": lambda: seeded.append("admin"),
            "site_content": lambda: seeded.append("site_content"),
        },
    )

    with TestClient(build_domain_app(DOMAINS[domain])) as client:
        client.get("/health")

    assert seeded == []


@pytest.mark.unit
def test_an_unknown_seed_name_is_rejected():
    """The descriptor names seeds by string, so a typo has to fail loudly
    rather than silently seeding nothing."""
    from app.core.middleware import SeedMiddleware

    with pytest.raises(ValueError, match="Unknown seed"):
        SeedMiddleware(lambda *a: None, seeds=("not_a_seed",))
