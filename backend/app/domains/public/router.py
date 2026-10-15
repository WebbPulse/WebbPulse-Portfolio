"""The public domain's router: the unauthenticated, unprefixed surface.

Mounts the service root and the health check with no prefix and no tags, and the
live system figures under `/api/v1/public`."""

from fastapi import APIRouter, Response

from app.common.version import VERSION

from .figures import FiguresResponse, current_figures
from .service import database_status

router = APIRouter()


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


FIGURES_MAX_AGE = 300
"""Seconds browsers and caches may reuse a figures response with figures in it."""

EMPTY_FIGURES_MAX_AGE = 60
"""Seconds an empty figures response may be reused, so a cold or failing cache retries soon."""


@router.get(
    "/api/v1/public/figures",
    tags=["public"],
    response_model=FiguresResponse,
    response_model_exclude_none=True,
)
def get_figures(response: Response) -> FiguresResponse:
    """Live public system figures, served from a cache refreshed about every 15 minutes."""
    figures = current_figures()
    max_age = FIGURES_MAX_AGE if figures else EMPTY_FIGURES_MAX_AGE
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return FiguresResponse(figures=figures)
