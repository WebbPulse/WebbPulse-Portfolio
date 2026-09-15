"""Repositories the identity domain reads and writes.

The instances live in `app.common.db.entities` so every entity shares one id allocator
and one domain can read a table it does not own.
"""

from app.common.db.entities import users

__all__ = ["users"]
