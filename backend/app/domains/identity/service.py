"""Seeding the single administrator, in both the legacy and the identity world.

With a credential store wired this owns the user row and the identity
credential; without one it reconciles the legacy column as before.
"""

from __future__ import annotations

from typing import Any

from ...config import settings
from ...core.logging import logger
from ...core.security import get_password_hash, verify_password
from ...db.repository import UniqueViolation
from .repository import users

_seeded = False

#: The legacy password column, named rather than spelled inline so the places
#: that must not touch it are greppable.
LEGACY_HASH_FIELD = "hashed_password"


def _ensure_credential(credential_store: Any, user_id: Any) -> None:
    """Create the admin's password credential, once, and never overwrite one.

    A `get` before a `put`, since the store's `put` is unconditional. Racing cold
    starts can only write the same seeded password twice.
    """
    from webbpulse.identity import PASSWORD_CREDENTIAL_TYPE, CredentialRecord

    subject = str(user_id)
    if credential_store.get(subject, PASSWORD_CREDENTIAL_TYPE) is not None:
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

    The two paths differ in exactly one respect, which is who owns the password:
    the credential store when it is supplied, the legacy column when it is not.
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
    legacy_hash = user.get(LEGACY_HASH_FIELD) or ""
    if not identity_mode and not verify_password(settings.ADMIN_PASSWORD, legacy_hash):
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
    """Seed the administrator on the first call in this process only."""
    global _seeded
    if _seeded:
        return
    seed_admin_user(credential_store)
    _seeded = True


def reset_seed_state() -> None:
    """Forget that seeding has run, so a test can trigger it again."""
    global _seeded
    _seeded = False
