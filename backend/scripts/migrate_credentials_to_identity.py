"""Copy each user's bcrypt password hash into the identity `credentials` table.

Legacy and identity hashes come from the same `webbpulse.security` functions, so
the copy is verbatim and idempotent. Dry run unless `--apply` is passed.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _name, _placeholder in (
    ("SECRET_KEY", "migration"),
    ("ADMIN_USERNAME", "migration"),
    ("ADMIN_PASSWORD", "migration"),
    ("ADMIN_EMAIL", "migration@example.com"),
):
    os.environ.setdefault(_name, _placeholder)

from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE  # noqa: E402

from app.db.tables import CREDENTIALS  # noqa: E402

LEGACY_HASH_FIELD = "hashed_password"
"""The legacy column holding the bcrypt hash on a Portfolio user row."""

BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")
"""Bcrypt modular crypt prefixes that `bcrypt.checkpw` still verifies; anything else
is not copied because the credential could never verify."""


class CredentialConflict(Exception):
    """A user already has a credential whose secret is not the legacy hash.

    Raised rather than resolved: only `--replace` may declare that the legacy
    column is the truth.
    """

    def __init__(self, conflicts):
        """Build the error from the conflicting user ids."""
        self.conflicts = conflicts
        detail = ", ".join(str(user_id) for user_id in conflicts)
        super().__init__(
            f"{len(conflicts)} user(s) already hold a different credential "
            f"({detail}); rerun with --replace to overwrite from the users table"
        )


class Decision(NamedTuple):
    """What one user needs, decided without writing anything.

    Carries the `secret` and `created_at` the write would use so `migrate`
    applies exactly the plan it printed.
    """

    user_id: str
    action: str
    detail: str
    secret: str = ""
    created_at: str = ""


def is_supported_hash(value):
    """Whether `value` is a bcrypt hash this migration may copy verbatim.

    Length as well as prefix, so a truncated hash is refused rather than
    written as a credential that can never verify.
    """
    if not isinstance(value, str):
        return False
    return value.startswith(BCRYPT_PREFIXES) and len(value) == 60


def build_store(prefix, endpoint_url=None):
    """Build the package credential store over the `credentials` table.

    Same construction the running service uses, so the items written here are
    the items the identity flow reads.
    """
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import DynamoCredentialStore

    return DynamoCredentialStore(
        Repository(CREDENTIALS, prefix=prefix, endpoint_url=endpoint_url)
    )


def plan(users_repository, store):
    """Decide what each user needs, touching nothing.

    Returns `Decision` rows whose action is `write`, `unchanged`, `conflict` or
    `skip`, so the dry run and `--apply` share one code path.
    """
    decisions = []
    for user in users_repository.list_all(include_inactive=True):
        user_id = str(user["id"])
        legacy = user.get(LEGACY_HASH_FIELD)

        if not legacy:
            decisions.append(
                Decision(user_id, "skip", "no legacy hash on the user row")
            )
            continue

        if not is_supported_hash(legacy):
            decisions.append(
                Decision(
                    user_id, "skip", "legacy hash is not a bcrypt modular crypt string"
                )
            )
            continue

        existing = store.get(user_id, PASSWORD_CREDENTIAL_TYPE)
        if existing is None:
            decisions.append(Decision(user_id, "write", "no credential yet", legacy))
        elif existing.secret == legacy:
            decisions.append(
                Decision(user_id, "unchanged", "credential already matches", legacy)
            )
        else:
            decisions.append(
                Decision(
                    user_id,
                    "conflict",
                    "credential differs from legacy hash",
                    legacy,
                    existing.created_at,
                )
            )
    return decisions


def migrate(users_repository, store, apply=False, replace=False):
    """Copy every migratable hash. Dry run unless `apply` is true.

    Raises `CredentialConflict` before writing anything when a user holds a
    different credential and `replace` was not passed.
    """
    from webbpulse.identity import CredentialRecord

    decisions = plan(users_repository, store)

    conflicts = [d.user_id for d in decisions if d.action == "conflict"]
    if conflicts and not replace:
        raise CredentialConflict(conflicts)

    summary = {"write": 0, "unchanged": 0, "conflict": 0, "skip": 0}
    for decision in decisions:
        summary[decision.action] += 1
        if decision.action in ("unchanged", "skip"):
            continue
        if not apply:
            continue

        store.put(
            CredentialRecord(
                user_id=decision.user_id,
                credential_type=PASSWORD_CREDENTIAL_TYPE,
                secret=decision.secret,
                created_at=decision.created_at,
            )
        )
    return summary, decisions


def report(summary, decisions, apply):
    """Print one line per decision plus the per-action totals."""
    mode = "applied" if apply else "dry run, nothing written"
    print(f"credential migration ({mode})")
    for decision in decisions:
        print(f"  user {decision.user_id}: {decision.action} ({decision.detail})")
    print(
        "  totals: "
        + ", ".join(f"{action}={count}" for action, count in summary.items())
    )


def parse_args(argv=None):
    """Parse the command line and export the prefix and endpoint.

    Both are written back into the environment before `main` imports anything
    that builds the `Settings` singleton, so one flag selects one environment.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Copy each user's bcrypt password hash into the identity "
            "credentials table. Dry run unless --apply is passed."
        )
    )
    parser.add_argument(
        "--prefix",
        default=os.environ.get("DYNAMODB_TABLE_PREFIX"),
        help=(
            "DynamoDB table prefix, covering both the identity credentials "
            "table and the legacy users table. Exported back into "
            "DYNAMODB_TABLE_PREFIX so one flag selects one environment "
            "(default: $DYNAMODB_TABLE_PREFIX)"
        ),
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.environ.get("DYNAMODB_ENDPOINT_URL"),
        help="DynamoDB endpoint (default: $DYNAMODB_ENDPOINT_URL, else AWS)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write; without it the script only prints the plan",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="overwrite a credential that differs from the legacy hash",
    )
    args = parser.parse_args(argv)
    if not args.prefix:
        parser.error("--prefix is required when DYNAMODB_TABLE_PREFIX is not set")

    os.environ["DYNAMODB_TABLE_PREFIX"] = args.prefix
    if args.endpoint_url:
        os.environ["DYNAMODB_ENDPOINT_URL"] = args.endpoint_url
    return args


def main(argv=None):
    """Run the migration and return the process exit code."""
    args = parse_args(argv)

    from app.db import entities

    store = build_store(args.prefix, args.endpoint_url)
    try:
        summary, decisions = migrate(
            entities.users, store, apply=args.apply, replace=args.replace
        )
    except CredentialConflict as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report(summary, decisions, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
