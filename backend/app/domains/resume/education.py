"""Education entry routes, built from the generic resume CRUD router."""

from ...db import ordering
from .crud_router import CrudConfig, build_crud_router
from .repository import education
from .schemas import Education, EducationCreate, EducationList, EducationUpdate

router = build_crud_router(
    CrudConfig(
        repository=education,
        schema=Education,
        list_schema=EducationList,
        create_schema=EducationCreate,
        update_schema=EducationUpdate,
        resource="education entries",
        not_found="Education entry not found",
        deleted_message="Education entry deleted successfully",
        order=ordering.education,
    )
)
