"""Repositories the identity domain reads and writes.

The instances live in `app.db.entities` so every entity shares one id allocator
and one domain can read a table it does not own.
"""

from ...db.entities import users

__all__ = ["users"]
