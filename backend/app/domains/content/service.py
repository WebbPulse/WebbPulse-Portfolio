"""Seeding of the site content singleton, done once per process."""

from botocore.exceptions import ClientError

from ...core.logging import logger
from .defaults import SITE_CONTENT_DEFAULTS
from .repository import SITE_CONTENT_ID, site_content

_seeded = False


def seed_site_content() -> None:
    """Create the site content row when it is absent.

    Tolerates losing the create race to another instance, since the row is a
    singleton and either writer produces the same one."""
    if site_content.get(SITE_CONTENT_ID) is not None:
        return
    try:
        site_content.create(SITE_CONTENT_DEFAULTS, item_id=SITE_CONTENT_ID)
        logger.info("Seeded site content", extra={"id": SITE_CONTENT_ID})
    except ClientError as error:
        if error.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        if site_content.get(SITE_CONTENT_ID) is None:
            raise


def ensure_site_content_seeded() -> None:
    """Seed on the first call in this process and do nothing afterwards."""
    global _seeded
    if _seeded:
        return
    seed_site_content()
    _seeded = True


def reset_seed_state() -> None:
    """Forget that seeding has run, so a test can seed again."""
    global _seeded
    _seeded = False
