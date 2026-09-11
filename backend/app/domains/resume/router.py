"""The resume domain's router: projects, experience, skills and credentials.

Applies the prefix and tag for each collection under a single mount point."""

from fastapi import APIRouter

from .certifications import router as certifications_router
from .education import router as education_router
from .experience import router as experience_router
from .projects import router as projects_router
from .skills import router as skills_router

router = APIRouter()

router.include_router(projects_router, prefix="/projects", tags=["projects"])
router.include_router(experience_router, prefix="/experience", tags=["experience"])
router.include_router(skills_router, prefix="/skills", tags=["skills"])
router.include_router(education_router, prefix="/education", tags=["education"])
router.include_router(
    certifications_router, prefix="/certifications", tags=["certifications"]
)
