from ...db import ordering
from .crud_router import CrudConfig, build_crud_router
from .repository import certifications
from .schemas import (
    Certification,
    CertificationCreate,
    CertificationList,
    CertificationUpdate,
)

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
