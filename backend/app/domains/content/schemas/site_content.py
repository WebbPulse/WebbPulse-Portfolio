from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AboutValue(BaseModel):
    title: str
    description: str
    icon: Optional[str] = None


class SiteContentBase(BaseModel):
    hero_title: str
    hero_subtitle: str
    hero_description: str
    about_paragraphs: List[str] = []
    about_values: List[AboutValue] = []
    profile_image_url: Optional[str] = None
    resume_url: Optional[str] = None
    email: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    footer_tagline: Optional[str] = None
    project_sort_mode: str = "manual"


class SiteContentUpdate(BaseModel):
    hero_title: Optional[str] = None
    hero_subtitle: Optional[str] = None
    hero_description: Optional[str] = None
    about_paragraphs: Optional[List[str]] = None
    about_values: Optional[List[AboutValue]] = None
    profile_image_url: Optional[str] = None
    resume_url: Optional[str] = None
    email: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    footer_tagline: Optional[str] = None
    project_sort_mode: Optional[str] = None


class SiteContent(SiteContentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
