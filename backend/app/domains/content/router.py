"""The content domain's router: posts, categories and the site content singleton.

The two halves are exported alongside the combined router so a composition root
can mount them separately."""

from fastapi import APIRouter

from .posts import router as posts_router
from .site_content import router as site_content_router

POSTS_PREFIX = "/posts"
POSTS_TAGS = ["posts"]
SITE_CONTENT_PREFIX = "/site-content"
SITE_CONTENT_TAGS = ["site-content"]

router = APIRouter()

router.include_router(posts_router, prefix=POSTS_PREFIX, tags=POSTS_TAGS)
router.include_router(site_content_router, prefix=SITE_CONTENT_PREFIX, tags=SITE_CONTENT_TAGS)

__all__ = [
    "POSTS_PREFIX",
    "POSTS_TAGS",
    "SITE_CONTENT_PREFIX",
    "SITE_CONTENT_TAGS",
    "posts_router",
    "router",
    "site_content_router",
]
