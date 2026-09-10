"""Copy each user's bcrypt password hash into the identity `credentials` table.

This is the data half of the identity cutover. M2 adoption put the identity
Lambda and its three tables in place; M3 adoption mounts the rest of the flows.
Neither moves a single existing password, so until this script runs the
`credentials` table is empty and the administrator can sign in through the
legacy `POST /api/v1/admin/login` and through nothing else. Running it is what
makes `VITE_AUTH_MODE=identity` a flip rather than a lockout.

`docs/identity-cutover.md` is the runbook and gives the order of operations.

## The hash copies verbatim, and here is why that is safe

The legacy column and the identity credential hold **the same bytes produced by
the same function**, so this migration is a copy and not a rehash.

- The legacy hash is written by `app/domains/identity/service.py:18`, which
  calls `get_password_hash` from `app/core/security.py`.
- That function is `app/core/security.py:96`, a one-line adapter returning
  `webbpulse.security.hash_password(password)`.
- The identity registration flow writes its credential at
  `webbpulse/identity/flows.py:281`, calling `hash_password` from the very same
  `webbpulse.security`.
- Verification matches too. Legacy login reaches `verify_password` in
  `app/core/security.py:84`, again `webbpulse.security.verify_password`, and the
  identity login flow calls that same function.

One bcrypt implementation, one cost, one encoded format. `webbpulse.security`
fixes `DEFAULT_ROUNDS = 12` and `BCRYPT_MAX_BYTES = 72`, and applies the 72 byte
truncation identically in both `hash_password` and `verify_password`, so a hash
written by the legacy seed verifies under the identity flow unchanged.
`backend/tests/test_security_compat.py` already pins that against hashes minted
by the pre-package code path.

So there is no "generate no password and reset later" case here. That branch
would apply to a product whose legacy hashes came from a different algorithm
family or a different encoded format, and Portfolio's do not. The script still
**validates** every hash it copies rather than assuming: `is_supported_hash`
rejects anything that is not a bcrypt modular crypt string, and a row carrying
one is skipped and reported instead of being written as an unverifiable secret.

## Idempotence, and what a rerun does

Safe to run repeatedly, which matters because the runbook runs it once per
environment and a half-finished run has to be resumable.

A user whose credential is already present with the same secret is left exactly
as it is, `created_at` included, and counted as `unchanged`. One whose stored
secret differs is only rewritten under `--replace`; without it the row is
reported as a conflict and the script exits non-zero, because a credential that
disagrees with the legacy column is either a password changed through the
identity flow after the cutover started or a migration run against the wrong
table, and both want a human rather than an overwrite.

`created_at` is preserved on an unchanged row rather than being refreshed. The
value is the moment the credential came into existence, and a rerun of a
migration is not a new credential.

## Dry run by default

Nothing is written unless `--apply` is passed. The default prints the plan and
exits, so the runbook's first step against production is always a read.

## Table names come from the environment, not from a constant

`--prefix` defaults to `DYNAMODB_TABLE_PREFIX`, which is what every function
already carries and what `app/db/tables.py` builds every table name from. The
logical names are the package's own `CREDENTIALS_TABLE` and this repository's
`users`, so a rename in either place travels here without an edit.

## The store is the package's, not a hand rolled PutItem

Writes go through `webbpulse.identity.DynamoCredentialStore` over a
`webbpulse.dynamodb.Repository`, which is the same pair
`app/composition/identity.py` builds for the running service. That is
deliberate: the item shape, the `created_at`/`updated_at` defaulting and the key
names are the package's problem, and a script writing its own item dict would be
a second implementation of a shape the package is free to change.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# `app.config` builds a `Settings` at import and refuses to construct without
# these. The migration reads users and writes credentials and authenticates
# nobody, so the values are placeholders and never reach a hash or a token.
# `setdefault` so a real environment that already carries them is left alone.
for _name, _placeholder in (
    ("SECRET_KEY", "migration"),
    ("ADMIN_USERNAME", "migration"),
    ("ADMIN_PASSWORD", "migration"),
    ("ADMIN_EMAIL", "migration@example.com"),
):
    os.environ.setdefault(_name, _placeholder)

# `PASSWORD_CREDENTIAL_TYPE` is the `credential_type` range key for a bcrypt
# password. Imported from the package rather than spelled `"password"` here, so
# this and the flow that reads the row cannot disagree about the key.
from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE  # noqa: E402

from app.db.tables import CREDENTIALS  # noqa: E402

#: The legacy column holding the bcrypt hash on a Portfolio user row.
LEGACY_HASH_FIELD = "hashed_password"

#: The bcrypt modular crypt prefixes. `$2b$` is what `bcrypt.hashpw` produces
#: today and what every Portfolio row carries; `$2a$` and `$2y$` are older
#: variants that the same `bcrypt.checkpw` still verifies, so a row carrying one
#: migrates rather than being refused. Anything else is not a bcrypt hash and is
#: not copied: writing it would produce a credential that can never verify.
BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


class CredentialConflict(Exception):
    """A user already has a credential whose secret is not the legacy hash.

    Raised rather than resolved, because the two ways to get here want opposite
    answers. A password changed through the identity flow after the cutover
    began must not be reverted to the legacy hash, and a run pointed at the
    wrong environment's tables must not write anything at all. `--replace` is
    the explicit way to say the legacy column is the truth.
    """

    def __init__(self, conflicts):
        self.conflicts = conflicts
        detail = ", ".join(str(user_id) for user_id in conflicts)
        super().__init__(
            f"{len(conflicts)} user(s) already hold a different credential "
            f"({detail}); rerun with --replace to overwrite from the users table"
        )


class Decision(NamedTuple):
    """What one user needs, decided without writing anything.

    Carries the `secret` and `created_at` the write would use, so `migrate`
    applies the plan it printed rather than re-reading the users table and
    deciding a second time. A rerun of the read could see a row edited between
    the two passes, which would apply something the dry run never showed.
    """

    user_id: str
    action: str
    detail: str
    secret: str = ""
    created_at: str = ""


def is_supported_hash(value):
    """Whether `value` is a bcrypt hash this migration may copy verbatim.

    A length check as well as a prefix check: a bcrypt string is 60 characters,
    and a truncated one would be copied happily by a prefix test alone and then
    fail every verification with no indication of why.
    """
    if not isinstance(value, str):
        return False
    return value.startswith(BCRYPT_PREFIXES) and len(value) == 60


def build_store(prefix, endpoint_url=None):
    """The package's `DynamoCredentialStore` over the `credentials` table.

    The same construction `app/composition/identity.py` uses for the running
    service, so the items this writes are the items that flow reads.
    """
    from webbpulse.dynamodb import Repository
    from webbpulse.identity import DynamoCredentialStore

    return DynamoCredentialStore(
        Repository(CREDENTIALS, prefix=prefix, endpoint_url=endpoint_url)
    )


def plan(users_repository, store):
    """Decide what each user needs, touching nothing.

    Returns a list of `(user_id, action, detail)`, where `action` is one of
    `write`, `unchanged`, `conflict` or `skip`. Separating the decision from the
    write is what lets `--apply` and the dry run share one code path and report
    the same thing.
    """
    decisions = []
    for user in users_repository.list_all(include_inactive=True):
        user_id = str(user["id"])
        legacy = user.get(LEGACY_HASH_FIELD)

        if not legacy:
            # A row created through the identity registration flow has no
            # legacy column at all: `create_user` in
            # `app/composition/identity_hooks.py` pops it deliberately. Its
            # credential already exists and there is nothing here to copy.
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

    Raises `CredentialConflict` when a user holds a different credential and
    `replace` was not passed, before writing anything at all: a run that would
    partially apply and then refuse is worse than one that refuses first.
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
                # Preserve the original creation moment when replacing, so a
                # rewrite records when the credential came into existence
                # rather than when the migration last touched it. The store
                # fills both in when they are empty.
                created_at=decision.created_at,
            )
        )
    return summary, decisions


def report(summary, decisions, apply):
    mode = "applied" if apply else "dry run, nothing written"
    print(f"credential migration ({mode})")
    for decision in decisions:
        print(f"  user {decision.user_id}: {decision.action} ({decision.detail})")
    print(
        "  totals: "
        + ", ".join(f"{action}={count}" for action, count in summary.items())
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Copy each user's bcrypt password hash into the identity "
            "credentials table. Dry run unless --apply is passed."
        )
    )
    parser.add_argument(
        "--prefix",
        default=os.environ.get("DYNAMODB_TABLE_PREFIX"),
        help="DynamoDB table prefix (default: $DYNAMODB_TABLE_PREFIX)",
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
    return args


def main(argv=None):
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
