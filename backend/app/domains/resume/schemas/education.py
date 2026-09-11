"""Request and response models for education entries."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EducationBase(BaseModel):
    """Fields every education entry representation carries."""

    degree: str
    school: str
    location: str
    period: str
    start_date: date
    end_date: Optional[date] = None
    description: Optional[str] = None
    order: int = 0


class EducationCreate(EducationBase):
    """A new education entry, identical to the base fields."""


class EducationUpdate(BaseModel):
    """A partial education entry edit; every field is optional."""

    degree: Optional[str] = None
    school: Optional[str] = None
    location: Optional[str] = None
    period: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class Education(EducationBase):
    """A stored education entry as returned to a client."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EducationList(BaseModel):
    """A education entry as it appears in a listing."""

    id: int
    degree: str
    school: str
    location: str
    period: str
    start_date: date
    end_date: Optional[date] = None
    description: Optional[str] = None
    order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
