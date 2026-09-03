from typing import List

from fastapi import Query

from ....db import ordering
from ....db.entities import SITE_CONTENT_ID, projects, site_content
from ....schemas import Project, ProjectCreate, ProjectList, ProjectUpdate
from ..crud_router import CrudConfig, build_crud_router

router = build_crud_router(
    CrudConfig(
        repository=projects,
        schema=Project,
        list_schema=ProjectList,
        create_schema=ProjectCreate,
        update_schema=ProjectUpdate,
        resource="projects",
        not_found="Project not found",
        deleted_message="Project deleted successfully",
        order=ordering.projects,
    ),
    include_list=False,
)


@router.get("/", response_model=List[ProjectList])
async def get_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    featured_only: bool = Query(False),
):
    items = projects.list_all()
    if featured_only:
        items = [item for item in items if item.get("featured")]
    content = site_content.get(SITE_CONTENT_ID)
    sort_mode = str(content.get("project_sort_mode", "manual")) if content else "manual"
    return ordering.projects(items, sort_mode)[skip : skip + limit]
