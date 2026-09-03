from .repository import PostRepository, Repository

SITE_CONTENT_ID = 1

users = Repository(
    "users",
    unique_fields=("username", "email"),
    defaults={"is_admin": False, "is_active": True},
)
categories = Repository("categories", unique_fields=("slug",))
posts = PostRepository("posts", unique_fields=("slug",))
projects = Repository(
    "projects",
    soft_delete=True,
    defaults={"technologies": list, "featured": False, "display_order": 0},
)
experience = Repository(
    "experience",
    soft_delete=True,
    defaults={"technologies": list, "achievements": list},
)
skills = Repository(
    "skills", soft_delete=True, defaults={"tier": "working", "order": 0}
)
education = Repository("education", soft_delete=True, defaults={"order": 0})
certifications = Repository("certifications", soft_delete=True, defaults={"order": 0})
site_content = Repository(
    "site-content",
    defaults={
        "about_paragraphs": list,
        "about_values": list,
        "project_sort_mode": "manual",
    },
)

BY_ENTITY = {
    repository.entity: repository
    for repository in (
        users,
        categories,
        posts,
        projects,
        experience,
        skills,
        education,
        certifications,
        site_content,
    )
}
