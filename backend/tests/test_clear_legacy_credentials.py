"""`scripts/clear_legacy_credentials.py` against moto and the real store.

Same shape as `test_credential_migration.py`, and for the same reason: the store
is the package's `DynamoCredentialStore` over the moto-backed tables
`conftest.py` creates, so what these tests assert about is the rows the identity
login flow actually reads.

The load bearing ones are the two refusals. A script that removed the only copy
of a password because it could not find the replacement would be the single
worst outcome of this cutover, so `mismatch` and `missing_credential` both stop
the run before anything is written and both exit non-zero.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE, CredentialRecord
from webbpulse.security import hash_password

from app.config import settings
from app.db import entities


def load_script():
    path = (
        Path(__file__).resolve().parents[1] / "scripts" / "clear_legacy_credentials.py"
    )
    spec = importlib.util.spec_from_file_location("clear_legacy_credentials", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load_script()


@pytest.fixture
def store(script):
    return script.build_store(settings.DYNAMODB_TABLE_PREFIX)


def make_user(password="legacy-password", username="admin", **overrides):
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
    store.put(
        CredentialRecord(
            user_id=str(user["id"]),
            credential_type=PASSWORD_CREDENTIAL_TYPE,
            secret=secret if secret is not None else user["hashed_password"],
        )
    )


def reload(user):
    return entities.users.get(user["id"], include_inactive=True)


class TestTheHappyPath:
    def test_a_dry_run_writes_nothing(self, script, store):
        user = make_user()
        give_credential(store, user)

        summary, decisions = script.clear(entities.users, store)

        assert summary["cleared"] == 1
        assert [d.action for d in decisions] == ["cleared"]
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_apply_removes_the_attribute_rather_than_emptying_it(self, script, store):
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
        user = make_user()
        give_credential(store, user)
        before = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)

        script.clear(entities.users, store, apply=True)

        after = store.get(str(user["id"]), PASSWORD_CREDENTIAL_TYPE)
        assert after.secret == before.secret
        assert after.created_at == before.created_at

    def test_a_rerun_reports_already_clear_and_exits_zero(self, script, store):
        user = make_user()
        give_credential(store, user)
        script.clear(entities.users, store, apply=True)

        summary, decisions = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 0
        assert summary["already_clear"] == 1
        assert [d.action for d in decisions] == ["already_clear"]
        assert "hashed_password" not in reload(user)

    def test_several_users_are_cleared_in_one_run(self, script, store):
        first = make_user(username="admin")
        second = make_user(username="second", password="another-password")
        give_credential(store, first)
        give_credential(store, second)

        summary, _ = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 2
        assert "hashed_password" not in reload(first)
        assert "hashed_password" not in reload(second)


class TestTheRefusals:
    def test_a_mismatch_refuses_and_writes_nothing(self, script, store):
        user = make_user()
        give_credential(store, user, secret=hash_password("a-different-password"))

        summary, decisions = script.clear(entities.users, store, apply=True)

        assert summary["mismatch"] == 1
        assert [d.action for d in decisions] == ["mismatch"]
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_a_missing_credential_refuses_and_writes_nothing(self, script, store):
        user = make_user()

        summary, decisions = script.clear(entities.users, store, apply=True)

        assert summary["missing_credential"] == 1
        assert [d.action for d in decisions] == ["missing_credential"]
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_one_bad_user_blocks_the_whole_run(self, script, store):
        """Refuse before writing anything, rather than half applying.

        A run that cleared the good users and then refused would leave an
        environment in a state neither script describes.
        """
        good = make_user(username="admin")
        bad = make_user(username="second", password="another-password")
        give_credential(store, good)

        summary, _ = script.clear(entities.users, store, apply=True)

        assert summary["cleared"] == 1
        assert summary["missing_credential"] == 1
        assert reload(good)["hashed_password"] == good["hashed_password"]
        assert reload(bad)["hashed_password"] == bad["hashed_password"]

    def test_a_row_with_neither_a_column_nor_a_credential_is_a_refusal(
        self, script, store
    ):
        """Not `already_clear`. A user with no password at all wants a human."""
        user = make_user()
        entities.users.update(user["id"], {"hashed_password": None})

        summary, decisions = script.clear(entities.users, store)

        assert summary["missing_credential"] == 1
        assert [d.action for d in decisions] == ["missing_credential"]


class TestTheExitCodeAndTheOutput:
    def test_main_exits_zero_on_a_clean_apply(self, script, store, capsys):
        user = make_user()
        give_credential(store, user)

        code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX, "--apply"])

        assert code == 0
        assert "hashed_password" not in reload(user)

    def test_main_exits_non_zero_on_a_mismatch(self, script, store, capsys):
        user = make_user()
        give_credential(store, user, secret=hash_password("a-different-password"))

        code = script.main(["--prefix", settings.DYNAMODB_TABLE_PREFIX, "--apply"])

        assert code == 1
        assert reload(user)["hashed_password"] == user["hashed_password"]

    def test_main_exits_non_zero_on_a_missing_credential(self, script, store):
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
        """The bug this pair of scripts shared.

        `--prefix` used to reach only the credential store, because the users
        repository reads `settings.DYNAMODB_TABLE_PREFIX` from the environment.
        `parse_args` now writes it back, which is what makes the documented
        command work without a second export.
        """
        monkeypatch.delenv("DYNAMODB_TABLE_PREFIX", raising=False)

        script.parse_args(["--prefix", "webbpulse-somewhere-else"])

        import os

        assert os.environ["DYNAMODB_TABLE_PREFIX"] == "webbpulse-somewhere-else"
