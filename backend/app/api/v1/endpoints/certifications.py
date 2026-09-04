from ....db import ordering
from ....db.entities import certifications
from ....schemas import (
    Certification,
    CertificationCreate,
    CertificationList,
    CertificationUpdate,
)
from ..crud_router import CrudConfig, build_crud_router

router = build_crud_router(
    CrudConfig(
        repository=certifications,
        schema=Certification,
        list_schema=CertificationList,
        create_schema=CertificationCreate,
        update_schema=CertificationUpdate,
        resource="certifications",
        not_found="Certification not found",
        deleted_message="Certification deleted successfully",
        order=ordering.certifications,
    )
)
