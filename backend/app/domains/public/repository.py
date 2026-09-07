"""Repositories the public domain reads.

Read only: the published posts index for the sitemap and the site-content
singleton for the health check.

The repository instances themselves live in ``app.db.entities``, not in this
package. Two things force that: ``app.core.security`` resolves the bearer token
against the user table on every authenticated request, and the id allocator in
``app.db.repository`` needs every entity registered in one place. Keeping the
instances shared is what lets a domain module read a table it does not own
without importing another domain's package.
"""

from ...db.entities import SITE_CONTENT_ID, posts, site_content

__all__ = ["SITE_CONTENT_ID", "posts", "site_content"]
