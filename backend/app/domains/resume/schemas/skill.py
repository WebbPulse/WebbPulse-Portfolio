"""Request and response models for skills."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

SkillCategory = Literal["frontend", "backend", "devops", "cloud", "networking", "other"]
SkillTier = Literal["core", "working", "familiar"]


class SkillBase(BaseModel):
    """Fields every skill representation carries."""

    name: str
    category: SkillCategory
    tier: SkillTier = "working"
    icon: Optional[str] = None
    order: int = 0


class SkillCreate(SkillBase):
    """A new skill, identical to the base fields."""


class SkillUpdate(BaseModel):
    """A partial skill edit; every field is optional."""

    name: Optional[str] = None
    category: Optional[SkillCategory] = None
    tier: Optional[SkillTier] = None
    icon: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class Skill(SkillBase):
    """A stored skill as returned to a client."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SkillList(BaseModel):
    """A skill as it appears in a listing."""

    id: int
    name: str
    category: SkillCategory
    tier: SkillTier
    icon: Optional[str] = None
    order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
