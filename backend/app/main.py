from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.api import api_router
from .config import settings
from .core.middleware import (
    MONOLITH_DOMAIN,
    DomainHeaderMiddleware,
    RequestLoggingMiddleware,
    SeedMiddleware,
    TrailingSlashMiddleware,
)
from .domains.public.router import router as public_router
from .version import VERSION

app = FastAPI(
    title=settings.APP_NAME,
    description="Blog API for Portfolio Website",
    version=VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)

app.include_router(api_router, prefix="/api/v1")
app.include_router(public_router)

app.add_middleware(SeedMiddleware)
app.add_middleware(TrailingSlashMiddleware, router=app.router)
app.add_middleware(RequestLoggingMiddleware)
# The monolith identifies itself too. A cut is verified by asking which
# function answered, and that question only has an answer if the function a
# route was moved off says so as clearly as the one it moved to.
app.add_middleware(DomainHeaderMiddleware, domain=MONOLITH_DOMAIN)
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
