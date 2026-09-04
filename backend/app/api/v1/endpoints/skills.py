from ....db import ordering
from ....db.entities import skills
from ....schemas import Skill, SkillCreate, SkillList, SkillUpdate
from ..crud_router import CrudConfig, build_crud_router

router = build_crud_router(
    CrudConfig(
        repository=skills,
        schema=Skill,
        list_schema=SkillList,
        create_schema=SkillCreate,
        update_schema=SkillUpdate,
        resource="skills",
        not_found="Skill not found",
        deleted_message="Skill deleted successfully",
        order=ordering.skills,
        default_limit=100,
        max_limit=200,
    )
)
