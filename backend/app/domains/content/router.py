"""The content domain's router: posts, categories and the site-content singleton.

``router`` is the whole domain in one object, prefixes and tags included, which
is what a per-domain application mounts under ``/api/v1``. ``posts_router`` and
``site_content_router`` are exported alongside it so the existing composition
root can keep mounting the two halves in their historical order and leave the
OpenAPI document byte for byte unchanged.
"""

from fastapi import APIRouter

from .posts import router as posts_router
from .site_content import router as site_content_router

POSTS_PREFIX = "/posts"
POSTS_TAGS = ["posts"]
SITE_CONTENT_PREFIX = "/site-content"
SITE_CONTENT_TAGS = ["site-content"]

router = APIRouter()

router.include_router(posts_router, prefix=POSTS_PREFIX, tags=POSTS_TAGS)
router.include_router(
    site_content_router, prefix=SITE_CONTENT_PREFIX, tags=SITE_CONTENT_TAGS
)

__all__ = [
    "POSTS_PREFIX",
    "POSTS_TAGS",
    "SITE_CONTENT_PREFIX",
    "SITE_CONTENT_TAGS",
    "posts_router",
    "router",
    "site_content_router",
]
