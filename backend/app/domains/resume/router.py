"""The resume domain's router: projects, experience, skills, education, certifications.

The prefixes and tags here are the ones the composition root used to apply
directly, so mounting this router under ``/api/v1`` produces the same paths,
tags and operation ids as before.
"""

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
