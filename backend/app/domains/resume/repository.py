"""Repositories the resume domain reads and writes.

The instances live in `app.common.db.entities` so every entity shares one id allocator
and one domain can read a table it does not own. `site_content` is read only."""

from app.common.db.entities import (
    SITE_CONTENT_ID,
    certifications,
    education,
    experience,
    projects,
    site_content,
    skills,
    users,
)

__all__ = [
    "SITE_CONTENT_ID",
    "certifications",
    "education",
    "experience",
    "projects",
    "site_content",
    "skills",
    "users",
]
