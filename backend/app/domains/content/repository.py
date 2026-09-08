"""Repositories the content domain reads and writes.

The repository instances themselves live in ``app.db.entities``, not in this
package. Two things force that: ``app.core.security`` resolves the bearer token
against the user table on every authenticated request, and the id allocator in
``app.db.repository`` needs every entity registered in one place. Keeping the
instances shared is what lets a domain module read a table it does not own
without importing another domain's package.
"""

from ...db.entities import SITE_CONTENT_ID, categories, posts, site_content, users

__all__ = ["SITE_CONTENT_ID", "categories", "posts", "site_content", "users"]
