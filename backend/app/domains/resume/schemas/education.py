from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EducationBase(BaseModel):
    degree: str
    school: str
    location: str
    period: str
    start_date: date
    end_date: Optional[date] = None
    description: Optional[str] = None
    order: int = 0


class EducationCreate(EducationBase):
    pass


class EducationUpdate(BaseModel):
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
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class EducationList(BaseModel):
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
