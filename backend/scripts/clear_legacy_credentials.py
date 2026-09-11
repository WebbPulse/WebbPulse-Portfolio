"""Remove the legacy `hashed_password` column once the identity migration holds.

The other half of `scripts/migrate_credentials_to_identity.py`. That script
copies each user's bcrypt hash into the identity `credentials` table and leaves
the legacy column exactly where it was; this one removes the column, and only
for a user whose credential is provably the same secret.

`docs/identity-cutover.md` is the runbook and gives the order: migrate, verify,
clear, flip `AUTH_MODE`, verify sign-in.

## Why clearing is a separate script and not part of the migration

Because the two are separated by a human verification. The migration writes into
a table nothing reads yet, so it is reversible by deleting rows nobody has used.
Clearing is the step that makes the identity store the only place the
administrator's password exists, and the runbook wants somebody to have signed
in through the identity path, or at least read the migration's output, before
that happens.

## What it will not do

**It never clears a column it cannot account for.** Each user is classified
before anything is written:

- `cleared`      the credential exists, its secret equals the legacy hash, and
                 the column was removed,
- `already_clear` there is no legacy column on the row, so there is nothing to
                 do, and a credential is still required to be present,
- `mismatch`     a credential exists but holds a different secret,
- `missing_credential` there is no password credential for this user at all,
- `errors`       the write itself failed.

`mismatch` and `missing_credential` are refusals rather than warnings, and the
process exits non-zero on either, because both mean removing the column would
take away a way into the account without having confirmed there is another one.
A `mismatch` in particular is usually benign, a password changed through
`POST /api/auth/password` after the migration ran, and the right answer to it is
still a human: the identity store is then correct and newer than the legacy
column, so the column can be cleared, but this script will not make that
judgement on its own.

## Removal, not an empty string

The attribute is REMOVEd. `Repository.update` turns a `None` value into a
DynamoDB `REMOVE` action, so passing `{"hashed_password": None}` deletes the
attribute rather than storing `""`.

That matters for more than tidiness. An empty string still reaches
`verify_password`, which answers `False` for it, so an empty column and a
missing one are the same to the login route. But an empty column is a value
somebody has to read as "deliberately blanked" rather than "never there", and a
row created by the identity registration flow already has no such attribute, so
removal is what makes a migrated row and a natively created row identical.

**Nothing in the backend requires the attribute to be present.** Checked before
writing this:

- `app/domains/identity/schemas/user.py` never mentions it. The `User` model
  carries `id`, `username`, `email`, `is_admin` and the timestamps, so no
  response model can fail on a missing column.
- `app/db/repository.py` builds items from whatever the row holds and applies
  `defaults` that do not include it, so `get`, `list_all` and `find_by_unique`
  all answer a row without it.
- `app/domains/identity/router.py` reads it with `.get(...) or _DUMMY_HASH`,
  which is the change that landed with this script, so the legacy login refuses
  a cleared user in constant time rather than raising KeyError.
- `app/domains/identity/service.py` no longer reads it at all when the identity
  credential store is wired, which is the change that makes clearing stick.

## Dry run by default

Nothing is written unless `--apply` is passed, on the same rule the migration
follows: the runbook's first run against an environment is always a read.

## No hash is ever printed

Not in the summary, not in a detail line, not in an error. The comparison is
made in memory and reported as a verdict. A script that printed the secret it
was about to delete would put the thing it is retiring into a terminal
scrollback and a CI log.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# `app.config` builds a `Settings` at import and refuses to construct without
# these. This script reads users and credentials and authenticates nobody, so
# the values are placeholders and never reach a hash or a token. `setdefault` so
# a real environment that already carries them is left alone.
for _name, _placeholder in (
    ("SECRET_KEY", "migration"),
    ("ADMIN_USERNAME", "migration"),
    ("ADMIN_PASSWORD", "migration"),
    ("ADMIN_EMAIL", "migration@example.com"),
):
    os.environ.setdefault(_name, _placeholder)

# Imported from the package rather than spelled `"password"` here, so this and
# the flow that reads the row cannot disagree about the key.
from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE  # noqa: E402

from app.db.tables import CREDENTIALS  # noqa: E402

#: The legacy column holding the bcrypt hash on a Portfolio user row. Same
#: constant as the migration's, deliberately duplicated rather than imported:
#: the two scripts run independently and one importing the other would make a
#: rename of either a runtime dependency between them.
LEGACY_HASH_FIELD = "hashed_password"

#: The actions that mean the run failed. Both are a user whose column would have
#: been removed without a confirmed replacement, which is the one outcome this
#: script exists to prevent.
FAILING_ACTIONS = ("mismatch", "missing_credential", "errors")

#: Every action, in the order the summary prints them.
ACTIONS = ("cleared", "already_clear", "mismatch", "missing_credential", "errors")


class Decision(NamedTuple):
    """What one user needs, decided without writing anything.

    Carries no secret of any kind. `detail` is a sentence for a human and is
    built from verdicts rather than from values, which is what keeps the
    no-hashes rule true by construction rather than by remembering it at each
    print site.
    """

    user_id: str
    action: str
    detail: str


def build_store(prefix, endpoint_url=None):
    """The package's `DynamoCredentialStore` over the `credentials` table.

    The same construction `app/composition/identity.py` uses for the running
    service and the same one the migration script uses, so the rows this reads
    are the rows that flow reads.
    """
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import DynamoCredentialStore

    return DynamoCredentialStore(
        Repository(CREDENTIALS, prefix=prefix, endpoint_url=endpoint_url)
    )


def plan(users_repository, store):
    """Classify every user, touching nothing.

    Separating the decision from the write is what lets the dry run and
    `--apply` report the same thing, and it is what lets the refusal below
    happen before a single row is touched.
    """
    decisions = []
    for user in users_repository.list_all(include_inactive=True):
        user_id = str(user["id"])
        legacy = user.get(LEGACY_HASH_FIELD)
        credential = store.get(user_id, PASSWORD_CREDENTIAL_TYPE)

        if credential is None:
            # Including the already-clear case. A row with no legacy column and
            # no credential is a user with no password at all, which is either
            # an OAuth-only or passkey-only account or a migration that has not
            # run, and neither is something to pass over silently.
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
    `missing_credential`. A run that removed half the columns and then refused
    would leave an environment in a state neither this script nor the migration
    describes, and the whole point of the classification is that it can be made
    without a write.
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
            # `None` is what `Repository.update` turns into a REMOVE action.
            # See the module docstring for why removal rather than `""`.
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

    # `--prefix` has to reach both the credential store and the legacy users
    # repository, and only the first is built from the parsed value: the second
    # reads `settings.DYNAMODB_TABLE_PREFIX`, which the `Settings` singleton
    # resolves from the environment at import. This happens in `parse_args`
    # because `main` imports `app.db.entities`, and that import is what builds
    # the singleton. Same fix, same reason, as the migration script.
    os.environ["DYNAMODB_TABLE_PREFIX"] = args.prefix
    if args.endpoint_url:
        os.environ["DYNAMODB_ENDPOINT_URL"] = args.endpoint_url
    return args


def main(argv=None):
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
