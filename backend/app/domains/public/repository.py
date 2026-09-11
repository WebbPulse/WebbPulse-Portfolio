"""Repositories the public domain reads.

Read only: published posts for the sitemap and the site content singleton for
the health check. The instances live in `app.db.entities`."""

from ...db.entities import SITE_CONTENT_ID, posts, site_content

__all__ = ["SITE_CONTENT_ID", "posts", "site_content"]
