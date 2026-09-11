"""Health reporting for the public domain.

Read only: the site-content singleton is the cheapest single-item read that
proves the DynamoDB path works end to end.
"""

from ...core.logging import logger
from .repository import SITE_CONTENT_ID, site_content


def database_status() -> str:
    """Report "healthy" when the site content read succeeds, "unhealthy" otherwise."""
    try:
        site_content.get(SITE_CONTENT_ID)
        return "healthy"
    except Exception as error:
        logger.exception("Database health check failed", extra={"error": str(error)})
        return "unhealthy"
