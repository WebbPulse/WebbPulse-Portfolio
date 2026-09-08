"""The public domain's router: the unauthenticated, unprefixed surface.

``GET /`` and ``GET /health`` used to be declared on the application object in
the monolith's ``app.main``; ``/sitemap.xml`` and ``/robots.txt`` came from the
SEO router.
Both are mounted here without a prefix and without tags, in the order the
application used to build them, so the route table and the OpenAPI document are
unchanged.
"""

from fastapi import APIRouter, Response

from ...version import VERSION
from .seo import router as seo_router
from .service import database_status

router = APIRouter()

router.include_router(seo_router)


@router.get("/")
async def root():
    return {"message": "Portfolio Blog API", "version": VERSION}


@router.get("/health")
async def health_check(response: Response):
    database = database_status()
    if database != "healthy":
        response.status_code = 503
    return {"status": "healthy", "database": database, "version": VERSION}
