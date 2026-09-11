"""The public domain's router: the unauthenticated, unprefixed surface.

Mounts the service root, the health check and the SEO documents with no prefix
and no tags."""

from fastapi import APIRouter, Response

from ...version import VERSION
from .seo import router as seo_router
from .service import database_status

router = APIRouter()

router.include_router(seo_router)


@router.get("/")
async def root():
    """The service name and version, for a quick reachability check."""
    return {"message": "Portfolio Blog API", "version": VERSION}


@router.get("/health")
async def health_check(response: Response):
    """Liveness plus a DynamoDB read, answering 503 when the read fails."""
    database = database_status()
    if database != "healthy":
        response.status_code = 503
    return {"status": "healthy", "database": database, "version": VERSION}
