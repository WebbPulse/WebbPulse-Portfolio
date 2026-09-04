from ....db import ordering
from ....db.entities import education
from ....schemas import Education, EducationCreate, EducationList, EducationUpdate
from ..crud_router import CrudConfig, build_crud_router

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
