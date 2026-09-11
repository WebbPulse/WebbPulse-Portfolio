"""Request and response models for work experience."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ExperienceBase(BaseModel):
    """Fields every experience entry representation carries."""

    title: str
    company: str
    location: str
    period: str
    start_date: date
    end_date: Optional[date] = None
    description: str
    technologies: List[str] = []
    achievements: List[str] = []


class ExperienceCreate(ExperienceBase):
    """A new experience entry, identical to the base fields."""


class ExperienceUpdate(BaseModel):
    """A partial experience entry edit; every field is optional."""

    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    period: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
    technologies: Optional[List[str]] = None
    achievements: Optional[List[str]] = None
    is_active: Optional[bool] = None


class Experience(ExperienceBase):
    """A stored experience entry as returned to a client."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExperienceList(BaseModel):
    """A experience entry as it appears in a listing."""

    id: int
    title: str
    company: str
    location: str
    period: str
    start_date: date
    end_date: Optional[date] = None
    description: str
    technologies: List[str] = []
    achievements: List[str] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
