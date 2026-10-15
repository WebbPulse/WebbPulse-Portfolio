"""Health reporting for the public domain.

A single item read on the public cache table, the cheapest call that proves the
DynamoDB path works end to end.
"""

from app.common.core.logging import logger
from app.common.db.client import table
from app.common.db.tables import PUBLIC_CACHE

HEALTH_KEY = "health"
"""The partition key the health read asks for. It need not exist."""


def database_status() -> str:
    """Report "healthy" when the cache table read succeeds, "unhealthy" otherwise."""
    try:
        table(PUBLIC_CACHE).get_item(Key={"pk": HEALTH_KEY})
        return "healthy"
    except Exception as error:
        logger.exception("Database health check failed", extra={"error": str(error)})
        return "unhealthy"
