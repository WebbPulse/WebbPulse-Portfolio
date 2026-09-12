"""`scripts/clear_legacy_credentials.py` against moto and the real store."""

import importlib.util
import sys
from pathlib import Path

import pytest
from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE, CredentialRecord
from webbpulse.security import hash_password

from app.config import settings
from app.db import entities


def load_script():
    """Import the clear script by path, since scripts is not a package."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "clear_legacy_credentials.py"
    spec = importlib.util.spec_from_file_location("clear_legacy_credentials", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    """The imported clear script, once per module."""
    return load_script()


@pytest.fixture
def store(script):
    """The credential store over the moto table conftest created."""
    return script.build_store(settings.DYNAMODB_TABLE_PREFIX)


def make_user(password="legacy-password", username="admin", **overrides):
    """A users row carrying a legacy bcrypt hash."""
    record = {
        "username": username,
        "email": f"{username}@example.com",
        "hashed_password": hash_password(password),
        "is_admin": True,
        "is_active": True,
    }
    record.update(overrides)
    return entities.users.create(record)


def give_credential(store, user, secret=None):
    """Write the matching identity credential for a user."""
    store.put(
        CredentialRecord(
            user_id=str(user["id"]),
            credential_type=PASSWORD_CREDENTIAL_TYPE,
            secret=secret if secret is not None else user["hashed_password"],
        )
    )


def reload(user):
    """Re-read a user row, inactive ones included."""
    return entities.users.get(user["id"], include_inactive=True)


class TestTheHappyPath:
    """Clearing the legacy column when the credential matches."""

    def test_a_dry_run_writes_nothing(self, script, store):
        """A dry run reports what it would clear and leaves the row alone."""
        user = make_user()
        give_credential(store, user)

        summary, decisions = script.clear(entities.users, store)

        assert summary["cleared"] == 1
        assert [d.action for d in decisions] == ["cleared"]
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_apply_removes_the_attribute_rather_than_emptying_it(self, script, store):
        """Applying removes the attribute and leaves the other fields intact."""
        user = make_user()
        give_credential(store, user)

        summary, _ = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 1
        refreshed = reload(user)
        assert "hashed_password" not in refreshed
        assert refreshed["username"] == user["username"]
        assert refreshed["email"] == user["email"]
        assert refreshed["is_admin"] is True
        assert refreshed["is_active"] is True

    def test_the_credential_is_not_touched(self, script, store):
        """Clearing the column leaves the identity credential unchanged."""
        user = make_user()
        give_credential(store, user)
        before = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)

        script.clear(entities.users, store, apply=True)

        after = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert after.secret == before.secret
        assert after.created_at == before.created_at

    def test_a_rerun_reports_already_clear_and_exits_zero(self, script, store):
        """A second run reports the row as already clear."""
        user = make_user()
        give_credential(store, user)
        script.clear(entities.users, store, apply=True)

        summary, decisions = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 0
        assert summary["already_clear"] == 1
        assert [d.action for d in decisions] == ["already_clear"]
        assert "hashed_password" not in reload(user)

    def test_several_users_are_cleared_in_one_run(self, script, store):
        """One run clears every eligible user."""
        first = make_user(username="admin")
        second = make_user(username="second", password="another-password")
        give_credential(store, first)
        give_credential(store, second)

        summary, _ = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 2
        assert "hashed_password" not in reload(first)
        assert "hashed_password" not in reload(second)


class TestTheRefusals:
    """The cases the script refuses to clear."""

    def test_a_mismatch_refuses_and_writes_nothing(self, script, store):
        """A credential that does not match the column is refused."""
        user = make_user()
        give_credential(store, user, secret=hash_password("a-different-password"))

        summary, decisions = script.clear(entities.users, store, apply=True)

        assert summary["mismatch"] == 1
        assert [d.action for d in decisions] == ["mismatch"]
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_a_missing_credential_refuses_and_writes_nothing(self, script, store):
        """A user with no identity credential is refused."""
        user = make_user()

        summary, decisions = script.clear(entities.users, store, apply=True)

        assert summary["missing_credential"] == 1
        assert [d.action for d in decisions] == ["missing_credential"]
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_one_bad_user_blocks_the_whole_run(self, script, store):
        """Refuse before writing anything, rather than half applying."""
        good = make_user(username="admin")
        bad = make_user(username="second", password="another-password")
        give_credential(store, good)

        summary, _ = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 1
        assert summary["missing_credential"] == 1
        assert reload(good)["hashed_password"] == good["hashed_password"]
        assert reload(bad)["hashed_password"] == bad["hashed_password"]

    def test_a_row_with_neither_a_column_nor_a_credential_is_a_refusal(self, script, store):
        """Not `already_clear`. A user with no password at all wants a human."""
        user = make_user()
        entities.users.update(user["id"], {"hashed_password": None})

        summary, decisions = script.clear(entities.users, store)

        assert summary["missing_credential"] == 1
        assert [d.action for d in decisions] == ["missing_credential"]


class TestTheExitCodeAndTheOutput:
    """What main returns and what it prints."""

    def test_main_exits_zero_on_a_clean_apply(self, script, store, capsys):
        """A clean apply exits zero."""
        user = make_user()
        give_credential(store, user)

        code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX, "--apply"])

        assert code == 0
        assert "hashed_password" not in reload(user)

    def test_main_exits_non_zero_on_a_mismatch(self, script, store, capsys):
        """A mismatch exits non-zero and writes nothing."""
        user = make_user()
        give_credential(store, user, secret=hash_password("a-different-password"))

        code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX, "--apply"])

        assert code == 1
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_main_exits_non_zero_on_a_missing_credential(self, script, store):
        """A missing credential exits non-zero."""
        make_user()

        code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX])

        assert code == 1

    def test_no_hash_is_ever_printed(self, script, store, capsys):
        """Every path, including the two refusals and the successful clear."""
        good = make_user(username="admin")
        give_credential(store, good)
        bad = make_user(username="second", password="another-password")
        give_credential(store, bad, secret=hash_password("something-else"))

        script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX, "--apply"])

        captured = capsys.readouterr()
        output = captured.out + captured.err
        for secret in (
            good["hashed_password"],
            bad["hashed_password"],
            store.get(str(bad["id"]), PASSWORD_CREDENTIAL_TYPE).secret,
        ):
            assert secret not in output
        assert "$2b$" not in output

    def test_the_prefix_flag_reaches_the_users_repository(self, script, monkeypatch):
        """The bug this pair of scripts shared."""
        monkeypatch.delenv("DYNAMODB_TABLE_PREFIX", raising=False)

        script.parse_args(["--prefix", "webbpulse-somewhere-else"])

        import os

        assert os.environ["DYNAMODB_TABLE_PREFIX"] == "webbpulse-somewhere-else"
