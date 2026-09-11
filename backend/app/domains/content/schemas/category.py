"""Request and response models for blog categories."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CategoryBase(BaseModel):
    """Fields every category representation carries."""

    name: str
    slug: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    """A new category; the slug is derived from the name when omitted."""

    slug: Optional[str] = None


class CategoryUpdate(BaseModel):
    """A partial category edit; every field is optional."""

    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None


class Category(CategoryBase):
    """A stored category as returned to a client."""

    id: int
    slug: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
