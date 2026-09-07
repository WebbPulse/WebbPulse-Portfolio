"""The v1 composition root.

Every route the application serves under ``/api/v1`` is mounted here, and
nowhere else. Each domain hands over routers that already know their own
prefixes and tags, so this file is the list of domains rather than the list of
resources.

The include order is the historical one, which keeps the ``paths`` map of the
OpenAPI document in exactly the order it has always been in. ``content`` is the
one domain mounted in two pieces for that reason: ``/posts`` has always come
first and ``/site-content`` has always come last.
"""

from fastapi import APIRouter

from ...domains.content import router as content_module
from ...domains.identity.router import router as identity_router
from ...domains.resume.router import router as resume_router

api_router = APIRouter()

api_router.include_router(
    content_module.posts_router,
    prefix=content_module.POSTS_PREFIX,
    tags=content_module.POSTS_TAGS,
)
api_router.include_router(identity_router, prefix="/admin", tags=["admin"])
api_router.include_router(resume_router)
api_router.include_router(
    content_module.site_content_router,
    prefix=content_module.SITE_CONTENT_PREFIX,
    tags=content_module.SITE_CONTENT_TAGS,
)
