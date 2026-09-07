from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .category import Category


class PostBase(BaseModel):
    title: str
    content: str
    excerpt: Optional[str] = None
    read_time: Optional[str] = None
    category_id: Optional[int] = None


class PostCreate(PostBase):
    slug: Optional[str] = None


class PostUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    read_time: Optional[str] = None
    category_id: Optional[int] = None
    published_at: Optional[datetime] = None


class Post(PostBase):
    id: int
    slug: str
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    category: Optional[Category] = None

    model_config = ConfigDict(from_attributes=True)


class PostList(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    read_time: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    category: Optional[Category] = None

    model_config = ConfigDict(from_attributes=True)
