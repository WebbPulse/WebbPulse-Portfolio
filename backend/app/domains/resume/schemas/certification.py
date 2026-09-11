"""Request and response models for certifications."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CertificationBase(BaseModel):
    """Fields every certification representation carries."""

    name: str
    issuer: str
    issued_date: date
    credential_url: Optional[str] = None
    order: int = 0


class CertificationCreate(CertificationBase):
    """A new certification, identical to the base fields."""


class CertificationUpdate(BaseModel):
    """A partial certification edit; every field is optional."""

    name: Optional[str] = None
    issuer: Optional[str] = None
    issued_date: Optional[date] = None
    credential_url: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class Certification(CertificationBase):
    """A stored certification as returned to a client."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CertificationList(BaseModel):
    """A certification as it appears in a listing."""

    id: int
    name: str
    issuer: str
    issued_date: date
    credential_url: Optional[str] = None
    order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
