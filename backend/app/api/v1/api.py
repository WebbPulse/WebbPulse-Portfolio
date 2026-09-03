from fastapi import APIRouter

from .endpoints import (
    admin,
    certifications,
    education,
    experience,
    posts,
    projects,
    site_content,
    skills,
)

api_router = APIRouter()

api_router.include_router(posts.router, prefix="/posts", tags=["posts"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(experience.router, prefix="/experience", tags=["experience"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(education.router, prefix="/education", tags=["education"])
api_router.include_router(
    certifications.router, prefix="/certifications", tags=["certifications"]
)
api_router.include_router(
    site_content.router, prefix="/site-content", tags=["site-content"]
)
