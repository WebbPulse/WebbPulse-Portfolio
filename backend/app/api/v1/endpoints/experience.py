from ....db import ordering
from ....db.entities import experience
from ....schemas import Experience, ExperienceCreate, ExperienceList, ExperienceUpdate
from ..crud_router import CrudConfig, build_crud_router

router = build_crud_router(
    CrudConfig(
        repository=experience,
        schema=Experience,
        list_schema=ExperienceList,
        create_schema=ExperienceCreate,
        update_schema=ExperienceUpdate,
        resource="experience entries",
        not_found="Experience entry not found",
        deleted_message="Experience entry deleted successfully",
        order=ordering.experience,
    )
)
