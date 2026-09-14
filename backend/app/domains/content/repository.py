"""Repositories the content domain reads and writes.

The instances live in `app.common.db.entities` so every entity shares one id allocator
and one domain can read a table it does not own."""

from app.common.db.entities import SITE_CONTENT_ID, categories, posts, site_content, users

__all__ = ["SITE_CONTENT_ID", "categories", "posts", "site_content", "users"]
