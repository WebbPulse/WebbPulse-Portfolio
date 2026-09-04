from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from .api.seo import router as seo_router
from .api.v1.api import api_router
from .config import settings
from .core.logging import logger
from .core.middleware import (
    RequestLoggingMiddleware,
    SeedMiddleware,
    TrailingSlashMiddleware,
)
from .db.entities import SITE_CONTENT_ID, site_content

VERSION = "1.0.0"

app = FastAPI(
    title=settings.APP_NAME,
    description="Blog API for Portfolio Website",
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(seo_router)


@app.get("/")
async def root():
    return {"message": "Portfolio Blog API", "version": VERSION}


def database_status() -> str:
    try:
        site_content.get(SITE_CONTENT_ID)
        return "healthy"
    except Exception as error:
        logger.exception("Database health check failed", error=str(error))
        return "unhealthy"


@app.get("/health")
async def health_check(response: Response):
    database = database_status()
    if database != "healthy":
        response.status_code = 503
    return {"status": "healthy", "database": database, "version": VERSION}


app.add_middleware(SeedMiddleware)
app.add_middleware(TrailingSlashMiddleware, router=app.router)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=["Content-Length", "Content-Type"],
    max_age=86400,
)
