"""Remove the legacy `hashed_password` column once the identity migration holds.

Clears only a user whose identity credential provably holds the same secret,
refusing the whole run otherwise. Dry run unless `--apply` is passed.
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

#: The legacy column holding the bcrypt hash on a Portfolio user row.
LEGACY_HASH_FIELD = "hashed_password"

#: Actions that mean the run failed: a column would have been removed without a
#: confirmed replacement.
FAILING_ACTIONS = ("mismatch", "missing_credential", "errors")

#: Every action, in the order the summary prints them.
ACTIONS = ("cleared", "already_clear", "mismatch", "missing_credential", "errors")


class Decision(NamedTuple):
    """What one user needs, decided without writing anything.

    Carries no secret: `detail` is built from verdicts, never from values, so
    no hash can reach a log.
    """

    user_id: str
    action: str
    detail: str


def build_store(prefix, endpoint_url=None):
    """Build the package credential store over the `credentials` table.

    Same construction the running service uses, so the rows read here are the
    rows the identity flow reads.
    """
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import DynamoCredentialStore

    return DynamoCredentialStore(
        Repository(CREDENTIALS, prefix=prefix, endpoint_url=endpoint_url)
    )


def plan(users_repository, store):
    """Classify every user, touching nothing.

    Deciding before writing lets the dry run and `--apply` report the same
    thing, and lets a refusal happen before any row is touched.
    """
    decisions = []
    for user in users_repository.list_all(include_inactive=True):
        user_id = str(user["id"])
        legacy = user.get(LEGACY_HASH_FIELD)
        credential = store.get(user_id, PASSWORD_CREDENTIAL_TYPE)

        if credential is None:
            decisions.append(
                Decision(
                    user_id,
                    "missing_credential",
                    "no password credential in the identity store",
                )
            )
            continue

        if not legacy:
            decisions.append(
                Decision(
                    user_id,
                    "already_clear",
                    "no legacy column on the row, credential present",
                )
            )
            continue

        if credential.secret != legacy:
            decisions.append(
                Decision(
                    user_id,
                    "mismatch",
                    "the credential holds a different secret from the legacy column",
                )
            )
            continue

        decisions.append(
            Decision(
                user_id, "cleared", "credential matches the legacy column, removing it"
            )
        )
    return decisions


def clear(users_repository, store, apply=False):
    """Remove the column for every user the plan cleared. Dry run unless `apply`.

    Refuses before writing anything when any user is a `mismatch` or a
    `missing_credential`, so a run never half applies.
    """
    decisions = plan(users_repository, store)
    summary = {action: 0 for action in ACTIONS}

    blocking = [d for d in decisions if d.action in ("mismatch", "missing_credential")]
    for decision in decisions:
        summary[decision.action] += 1
    if blocking:
        return summary, decisions

    if not apply:
        return summary, decisions

    written = []
    for decision in decisions:
        if decision.action != "cleared":
            written.append(decision)
            continue
        try:
            users_repository.update(int(decision.user_id), {LEGACY_HASH_FIELD: None})
            written.append(decision)
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            summary["cleared"] -= 1
            summary["errors"] += 1
            written.append(
                Decision(
                    decision.user_id,
                    "errors",
                    f"the write failed: {type(error).__name__}",
                )
            )
    return summary, written


def report(summary, decisions, apply):
    """Print one line per decision, the totals, and any refusal."""
    mode = "applied" if apply else "dry run, nothing written"
    print(f"legacy credential clearing ({mode})")
    for decision in decisions:
        print(f"  user {decision.user_id}: {decision.action} ({decision.detail})")
    print("  totals: " + ", ".join(f"{action}={summary[action]}" for action in ACTIONS))
    blocking = sum(summary[action] for action in FAILING_ACTIONS)
    if blocking:
        print(
            f"  refused: {blocking} user(s) are not safe to clear. Nothing was "
            "written. Confirm the migration has run for this environment and "
            "that every user holds a password credential.",
            file=sys.stderr,
        )


def parse_args(argv=None):
    """Parse the command line and export the prefix and endpoint.

    Both are written back into the environment before `main` imports anything
    that builds the `Settings` singleton, so one flag selects one environment.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Remove the legacy hashed_password column from every user whose "
            "identity password credential matches it. Dry run unless --apply "
            "is passed."
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
    args = parser.parse_args(argv)
    if not args.prefix:
        parser.error("--prefix is required when DYNAMODB_TABLE_PREFIX is not set")

    os.environ["DYNAMODB_TABLE_PREFIX"] = args.prefix
    if args.endpoint_url:
        os.environ["DYNAMODB_ENDPOINT_URL"] = args.endpoint_url
    return args


def main(argv=None):
    """Run the clearing pass and return the process exit code."""
    args = parse_args(argv)

    from app.db import entities

    store = build_store(args.prefix, args.endpoint_url)
    summary, decisions = clear(entities.users, store, apply=args.apply)
    report(summary, decisions, args.apply)
    if any(summary[action] for action in FAILING_ACTIONS):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
