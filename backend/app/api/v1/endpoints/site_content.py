from fastapi import APIRouter, Depends, HTTPException

from ....core.security import get_current_user, require_admin
from ....db.entities import SITE_CONTENT_ID, site_content
from ....schemas import SiteContent, SiteContentUpdate

router = APIRouter()


def _load():
    content = site_content.get(SITE_CONTENT_ID)
    if content is None:
        raise HTTPException(status_code=500, detail="Site content not initialized")
    return content


@router.get("/", response_model=SiteContent)
async def get_site_content():
    return _load()


@router.put("/", response_model=SiteContent)
async def update_site_content(
    update: SiteContentUpdate,
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user, "Not authorized to update site content")
    _load()
    return site_content.update(SITE_CONTENT_ID, update.model_dump(exclude_unset=True))
