"""`scripts/migrate_credentials_to_identity.py` against moto and the real store."""

import importlib.util
import sys
from pathlib import Path

import pytest
from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE, CredentialRecord
from webbpulse.security import hash_password, verify_password

from app.config import settings
from app.db import entities


def load_script():
    """Import the migration script by path, since scripts is not a package."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_credentials_to_identity.py"
    spec = importlib.util.spec_from_file_location("migrate_credentials_to_identity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    """The imported migration script, once per module."""
    return load_script()


@pytest.fixture
def store(script):
    """The real `DynamoCredentialStore` over the moto table `conftest` created."""
    return script.build_store(settings.DYNAMODB_TABLE_PREFIX)


def make_user(password="legacy-password", **overrides):
    """A users row shaped like the one `seed_admin_user` writes."""
    record = {
        "username": "admin",
        "email": "admin@example.com",
        "hashed_password": hash_password(password),
        "is_admin": True,
        "is_active": True,
    }
    record.update(overrides)
    return entities.users.create(record)


def test_a_dry_run_writes_nothing(script, store):
    """A dry run reports what it would write and stores nothing."""
    user = make_user()

    summary, decisions = script.migrate(entities.users, store)

    assert summary["write"] == 1
    assert [d.action for d in decisions] == ["write"]
    assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is None


def test_apply_writes_the_credential_in_the_packages_shape(script, store):
    """Applying writes a credential carrying the legacy hash and both timestamps."""
    user = make_user()

    summary, _ = script.migrate(entities.users, store, apply=True)

    assert summary["write"] == 1
    credential = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
    assert credential is not None
    assert credential.user_id == str(user["id"])
    assert credential.credential_type == PASSWORD_CREDENTIAL_TYPE
    assert credential.secret == user["hashed_password"]
    assert credential.created_at
    assert credential.updated_at


def test_the_migrated_hash_verifies_through_the_package(script, store):
    """The whole claim of the migration, end to end."""
    make_user(password="correct-horse-battery")

    script.migrate(entities.users, store, apply=True)

    credential = store.get("1", PASSWORD_CREDENTIAL_TYPE)
    assert verify_password("correct-horse-battery", credential.secret) is True
    assert verify_password("wrong-password", credential.secret) is False


def test_a_rerun_is_idempotent_and_preserves_created_at(script, store):
    """A second run changes nothing, timestamps included."""
    user = make_user()

    script.migrate(entities.users, store, apply=True)
    first = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)

    summary, decisions = script.migrate(entities.users, store, apply=True)

    assert summary == {"write": 0, "unchanged": 1, "conflict": 0, "skip": 0}
    assert [d.action for d in decisions] == ["unchanged"]
    second = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
    assert second.secret == first.secret
    assert second.created_at == first.created_at
    assert second.updated_at == first.updated_at


def test_a_differing_credential_is_a_conflict_and_nothing_is_written(script, store):
    """A password changed through the identity flow must not be reverted."""
    user = make_user()
    changed = hash_password("changed-through-identity")
    store.put(
        CredentialRecord(
            user_id=str(user["id"]),
            credential_type=PASSWORD_CREDENTIAL_TYPE,
            secret=changed,
        )
    )

    with pytest.raises(script.CredentialConflict) as error:
        script.migrate(entities.users, store, apply=True)

    assert str(user["id"]) in error.value.conflicts
    assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE).secret == changed


def test_replace_overwrites_a_conflict_but_keeps_created_at(script, store):
    """With replace, a conflicting credential is overwritten but keeps created_at."""
    user = make_user()
    store.put(
        CredentialRecord(
            user_id=str(user["id"]),
            credential_type=PASSWORD_CREDENTIAL_TYPE,
            secret=hash_password("changed-through-identity"),
            created_at="2020-01-01T00:00:00Z",
        )
    )

    summary, _ = script.migrate(entities.users, store, apply=True, replace=True)

    assert summary["conflict"] == 1
    credential = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
    assert credential.secret == user["hashed_password"]
    assert credential.created_at == "2020-01-01T00:00:00Z"


def test_a_user_with_no_legacy_hash_is_skipped(script, store):
    """A row created by the identity registration flow pops `hashed_password`."""
    user = entities.users.create(
        {
            "username": "registered",
            "email": "registered@example.com",
            "is_admin": False,
            "is_active": True,
        }
    )

    summary, decisions = script.migrate(entities.users, store, apply=True)

    assert summary["skip"] == 1
    assert decisions[0].detail == "no legacy hash on the user row"
    assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is None


def test_a_non_bcrypt_hash_is_skipped_rather_than_copied(script, store):
    """Copying an unrecognised secret would write a credential that never verifies."""
    user = make_user()
    entities.users.update(user["id"], {"hashed_password": "pbkdf2_sha256$..."})

    summary, decisions = script.migrate(entities.users, store, apply=True)

    assert summary["skip"] == 1
    assert "not a bcrypt" in decisions[0].detail
    assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is None


def test_an_inactive_user_still_migrates(script, store):
    """`may_authenticate` is the gate, not this script."""
    user = make_user(is_active=False)

    summary, _ = script.migrate(entities.users, store, apply=True)

    assert summary["write"] == 1
    assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is not None


@pytest.mark.parametrize(
    "value,supported",
    [
        ("$2b$12$" + "a" * 53, True),
        ("$2a$12$" + "a" * 53, True),
        ("$2y$12$" + "a" * 53, True),
        ("$2b$12$tooshort", False),
        ("pbkdf2_sha256$390000$salt$hash", False),
        ("", False),
        (None, False),
    ],
)
def test_is_supported_hash(script, value, supported):
    """Only bcrypt hashes of the right length are treated as migratable."""
    assert script.is_supported_hash(value) is supported


def test_parse_args_requires_a_prefix(script, monkeypatch):
    """With no prefix given or in the environment, argument parsing exits."""
    monkeypatch.delenv("DYNAMODB_TABLE_PREFIX", raising=False)
    with pytest.raises(SystemExit):
        script.parse_args([])


def test_parse_args_defaults_the_prefix_from_the_environment(script, monkeypatch):
    """The prefix falls back to the environment, and both flags default off."""
    monkeypatch.setenv("DYNAMODB_TABLE_PREFIX", "webbpulse-staging")
    args = script.parse_args([])
    assert args.prefix == "webbpulse-staging"
    assert args.apply is False
    assert args.replace is False


def test_main_dry_runs_by_default_and_reports(script, capsys):
    """Without apply, main dry runs, says so and writes nothing."""
    user = make_user()

    exit_code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX])

    assert exit_code == 0
    assert "dry run, nothing written" in capsys.readouterr().out
    store = script.build_store(settings.DYNAMODB_TABLE_PREFIX)
    assert store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE) is None


def test_main_returns_one_on_a_conflict(script, store, capsys):
    """A conflict exits one and points at the replace flag."""
    user = make_user()
    store.put(
        CredentialRecord(
            user_id=str(user["id"]),
            credential_type=PASSWORD_CREDENTIAL_TYPE,
            secret=hash_password("changed-through-identity"),
        )
    )

    exit_code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX, "--apply"])

    assert exit_code == 1
    assert "--replace" in capsys.readouterr().err
