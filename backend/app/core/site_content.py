from botocore.exceptions import ClientError

from ..db.entities import SITE_CONTENT_ID, site_content
from .logging import logger
from .site_content_defaults import SITE_CONTENT_DEFAULTS

_seeded = False


def seed_site_content() -> None:
    if site_content.get(SITE_CONTENT_ID) is not None:
        return
    try:
        site_content.create(SITE_CONTENT_DEFAULTS, item_id=SITE_CONTENT_ID)
        logger.info("Seeded site content", id=SITE_CONTENT_ID)
    except ClientError as error:
        if error.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        if site_content.get(SITE_CONTENT_ID) is None:
            raise


def ensure_site_content_seeded() -> None:
    global _seeded
    if _seeded:
        return
    seed_site_content()
    _seeded = True


def reset_seed_state() -> None:
    global _seeded
    _seeded = False
