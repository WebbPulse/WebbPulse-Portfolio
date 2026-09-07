from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ExperienceBase(BaseModel):
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
    pass


class ExperienceUpdate(BaseModel):
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
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExperienceList(BaseModel):
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
