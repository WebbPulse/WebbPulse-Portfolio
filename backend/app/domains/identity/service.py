"""Seeding the single administrator, in both the legacy and the identity world.

## Why this file changed at the cutover

The seeder used to be the reason the legacy `hashed_password` column could not
be emptied. It ran on the first request in every cold process and did this:

    if not verify_password(settings.ADMIN_PASSWORD, user["hashed_password"]):
        changes["hashed_password"] = get_password_hash(settings.ADMIN_PASSWORD)

`verify_password` answers `False` for an empty or absent stored hash, so a
column cleared by hand was repopulated within seconds of the next request, with
a **freshly salted** bcrypt hash. Bcrypt salts per call, so the new value was
never byte-identical to the one already migrated into the identity
`credentials` table, and the next run of
`scripts/migrate_credentials_to_identity.py` reported a `conflict` on a user
nobody had touched.

So the clearing script could not have worked while this file looked like that,
and the two changes belong in one commit.

## What it does now

**When the identity credential store is wired**, this seeder owns the user row
and the identity credential, and never the legacy column:

- the row is reconciled exactly as before for `email`, `is_admin` and
  `is_active`,
- `hashed_password` is neither read nor written, so a cleared column stays
  cleared and a populated one is left exactly as it is for the clearing script
  to deal with,
- a password credential is created in the store from `settings.ADMIN_PASSWORD`
  **only when no credential row exists at all**.

That last rule is the important one and it is deliberately not a reconcile. An
existing credential is never compared against `ADMIN_PASSWORD` and never
overwritten, because the administrator is expected to change their password
through `POST /api/auth/password` once the cutover is done, and a seeder that
reconciled would silently revert that change on the next cold start. The
credential is seeded for exactly one case: a brand new environment whose
`users` row this call just created, where nothing has ever set a password.

**When the store is not wired**, which is a local checkout, the test suite and
any function built without `IDENTITY_ISSUER`, the old behaviour is kept
unchanged, legacy reconcile included. That path still exists because
`POST /api/v1/admin/login` still exists; both go at M9.

## Why the store arrives as an argument

`app/domains/` may not import `app/composition/`, which
`tests/test_domain_boundaries.py` enforces, and the credential store is built
by `app/composition/identity.py` out of settings this domain does not read. So
the store is passed in rather than reached for, and `app/core/middleware.py`,
which is already the one module allowed to know about more than one domain, is
what resolves it and hands it over.

The resolution is cached for the life of the process rather than repeated per
request, and the warm path stays what it has always been: a module-level flag
checked and returned from.
"""

from __future__ import annotations

from typing import Any

from ...config import settings
from ...core.logging import logger
from ...core.security import get_password_hash, verify_password
from ...db.repository import UniqueViolation
from .repository import users

_seeded = False

#: The legacy column. Named rather than spelled inline because the whole point
#: of the identity path below is that it does not touch this, and a constant is
#: easier to grep for than a string literal in three places.
LEGACY_HASH_FIELD = "hashed_password"


def _ensure_credential(credential_store: Any, user_id: Any) -> None:
    """Create the admin's password credential, once, and never overwrite one.

    A `get` before a `put` rather than a conditional write: the store's own
    `put` is an unconditional `PutItem`, so the check has to happen here, and a
    race between two cold starts of the same function resolves to two identical
    writes of the same seeded password rather than to a lost user-chosen one.
    The window is the width of one GetItem on the first request of a brand new
    environment, and the only value either writer can produce is a hash of
    `ADMIN_PASSWORD`.
    """
    from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE, CredentialRecord

    subject = str(user_id)
    if credential_store.get(subject, PASSWORD_CREDENTIAL_TYPE) is not None:
        # Present already, whatever it holds. Not compared and not replaced:
        # see the module docstring. A password changed through the identity
        # flow is the case this protects.
        return

    credential_store.put(
        CredentialRecord(
            user_id=subject,
            credential_type=PASSWORD_CREDENTIAL_TYPE,
            secret=get_password_hash(settings.ADMIN_PASSWORD),
        )
    )
    logger.info(
        "Seeded admin identity credential",
        extra={"username": settings.ADMIN_USERNAME},
    )


def seed_admin_user(credential_store: Any = None) -> None:
    """Reconcile the administrator's row, and their credential where there is one.

    `credential_store` is a `webbpulse.identity.CredentialStore` when the
    identity flows are wired and `None` otherwise. The two paths differ in
    exactly one respect, which is who owns the password: the store when it is
    supplied, the legacy column when it is not.
    """
    identity_mode = credential_store is not None

    user = users.find_by_unique("username", settings.ADMIN_USERNAME)
    if user is None:
        record = {
            "username": settings.ADMIN_USERNAME,
            "email": settings.ADMIN_EMAIL,
            "is_admin": True,
            "is_active": True,
        }
        if not identity_mode:
            # In identity mode the row is created without the legacy column at
            # all, on the same rule `create_user` in
            # `app/composition/identity_hooks.py` follows: a row carrying a
            # hash the identity store does not know about is a second password
            # nobody is tracking.
            record[LEGACY_HASH_FIELD] = get_password_hash(settings.ADMIN_PASSWORD)
        try:
            user = users.create(record)
            logger.info(
                "Seeded admin user", extra={"username": settings.ADMIN_USERNAME}
            )
        except UniqueViolation:
            user = users.find_by_unique("username", settings.ADMIN_USERNAME)
            if user is None:
                raise
        else:
            if identity_mode:
                _ensure_credential(credential_store, user["id"])
            return

    changes = {}
    if user.get("email") != settings.ADMIN_EMAIL:
        changes["email"] = settings.ADMIN_EMAIL
    if not identity_mode and not verify_password(
        settings.ADMIN_PASSWORD, user.get(LEGACY_HASH_FIELD) or ""
    ):
        # `user.get(...) or ""` rather than `user[...]`, because the column is
        # removed outright by `scripts/clear_legacy_credentials.py` and a
        # subscript would raise KeyError on a cleared row. This branch cannot
        # run in identity mode, but the read has to be safe in both: legacy
        # mode is also what a local checkout runs, and a developer pointing one
        # at a cleared table should get a reseed rather than a 500.
        changes[LEGACY_HASH_FIELD] = get_password_hash(settings.ADMIN_PASSWORD)
    if not user.get("is_admin"):
        changes["is_admin"] = True
    if not user.get("is_active", True):
        changes["is_active"] = True
    if changes:
        users.update(user["id"], changes)
        logger.info(
            "Updated admin user from settings",
            extra={"username": settings.ADMIN_USERNAME},
        )

    if identity_mode:
        _ensure_credential(credential_store, user["id"])


def ensure_admin_seeded(credential_store: Any = None) -> None:
    global _seeded
    if _seeded:
        return
    seed_admin_user(credential_store)
    _seeded = True


def reset_seed_state() -> None:
    global _seeded
    _seeded = False
