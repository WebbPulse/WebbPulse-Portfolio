"""Routes reading and editing the site content singleton."""

from fastapi import APIRouter, Depends, HTTPException

from ...core.security import CurrentUser, require_admin
from .repository import SITE_CONTENT_ID, site_content
from .schemas import SiteContent, SiteContentUpdate

router = APIRouter()


def _load():
    """The site content row, or a 500 when seeding has not run."""
    content = site_content.get(SITE_CONTENT_ID)
    if content is None:
        raise HTTPException(status_code=500, detail="Site content not initialized")
    return content


@router.get("/", response_model=SiteContent)
async def get_site_content():
    """The site content singleton."""
    return _load()


@router.put("/", response_model=SiteContent)
async def update_site_content(
    update: SiteContentUpdate,
    current_user: dict = Depends(CurrentUser),
):
    """Apply a partial edit to the site content singleton. Admin only."""
    require_admin(current_user, "Not authorized to update site content")
    _load()
    return site_content.update(SITE_CONTENT_ID, update.model_dump(exclude_unset=True))
