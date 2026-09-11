"""Request and response models for blog posts."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .category import Category


class PostBase(BaseModel):
    """Fields every post representation carries."""

    title: str
    content: str
    excerpt: Optional[str] = None
    read_time: Optional[str] = None
    category_id: Optional[int] = None


class PostCreate(PostBase):
    """A new post; the slug is derived from the title when omitted."""

    slug: Optional[str] = None


class PostUpdate(BaseModel):
    """A partial post edit; every field is optional."""

    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    read_time: Optional[str] = None
    category_id: Optional[int] = None
    published_at: Optional[datetime] = None


class Post(PostBase):
    """A stored post with its category expanded."""

    id: int
    slug: str
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    category: Optional[Category] = None

    model_config = ConfigDict(from_attributes=True)


class PostList(BaseModel):
    """A post as it appears in a listing, without the body."""

    id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    read_time: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    category: Optional[Category] = None

    model_config = ConfigDict(from_attributes=True)
