from ..config import settings
from ..db.entities import users
from ..db.repository import UniqueViolation
from .logging import logger
from .security import get_password_hash, verify_password

_seeded = False


def seed_admin_user() -> None:
    user = users.find_by_unique("username", settings.ADMIN_USERNAME)
    if user is None:
        try:
            users.create(
                {
                    "username": settings.ADMIN_USERNAME,
                    "email": settings.ADMIN_EMAIL,
                    "hashed_password": get_password_hash(settings.ADMIN_PASSWORD),
                    "is_admin": True,
                    "is_active": True,
                }
            )
            logger.info("Seeded admin user", username=settings.ADMIN_USERNAME)
            return
        except UniqueViolation:
            user = users.find_by_unique("username", settings.ADMIN_USERNAME)
            if user is None:
                raise

    changes = {}
    if user.get("email") != settings.ADMIN_EMAIL:
        changes["email"] = settings.ADMIN_EMAIL
    if not verify_password(settings.ADMIN_PASSWORD, user["hashed_password"]):
        changes["hashed_password"] = get_password_hash(settings.ADMIN_PASSWORD)
    if not user.get("is_admin"):
        changes["is_admin"] = True
    if not user.get("is_active", True):
        changes["is_active"] = True
    if changes:
        users.update(user["id"], changes)
        logger.info(
            "Updated admin user from settings", username=settings.ADMIN_USERNAME
        )


def ensure_admin_seeded() -> None:
    global _seeded
    if _seeded:
        return
    seed_admin_user()
    _seeded = True


def reset_seed_state() -> None:
    global _seeded
    _seeded = False
