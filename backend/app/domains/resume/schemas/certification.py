from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CertificationBase(BaseModel):
    name: str
    issuer: str
    issued_date: date
    credential_url: Optional[str] = None
    order: int = 0


class CertificationCreate(CertificationBase):
    pass


class CertificationUpdate(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    issued_date: Optional[date] = None
    credential_url: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None


class Certification(CertificationBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CertificationList(BaseModel):
    id: int
    name: str
    issuer: str
    issued_date: date
    credential_url: Optional[str] = None
    order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
