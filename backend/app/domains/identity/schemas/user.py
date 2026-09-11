"""Request and response models for users and legacy password login."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Fields every user representation carries."""

    username: str
    email: EmailStr


class UserCreate(UserBase):
    """A new user, with the plaintext password to hash."""

    password: str


class UserUpdate(BaseModel):
    """A partial user edit; every field is optional."""

    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class User(UserBase):
    """A stored user as returned to a client, never carrying a secret."""

    id: int
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    """Credentials posted to the legacy login route."""

    username: str = Field(..., min_length=1, description="Username cannot be empty")
    password: str = Field(..., min_length=1, description="Password cannot be empty")


class Token(BaseModel):
    """A bearer access token and its type."""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """The claims read back out of a verified access token."""

    username: Optional[str] = None
