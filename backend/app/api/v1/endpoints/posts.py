from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from slugify import slugify

from ....core.security import get_current_user, require_admin
from ....db import ordering
from ....db.entities import categories, posts
from ....db.repository import UniqueViolation
from ....schemas import Category as CategorySchema
from ....schemas import CategoryCreate, CategoryUpdate
from ....schemas import Post as PostSchema
from ....schemas import PostCreate, PostList, PostUpdate

router = APIRouter()

POST_SLUG_TAKEN = "Post with this slug already exists"
CATEGORY_SLUG_TAKEN = "Category with this slug already exists"


def _with_categories(items):
    lookup = categories.get_many(item.get("category_id") for item in items)
    for item in items:
        item["category"] = lookup.get(item.get("category_id"))
    return items


def _with_category(item):
    return _with_categories([item])[0]


def _published(post):
    return post is not None and post.get("published_at") is not None


def _require_category(category_id):
    if category_id is not None and categories.get(category_id) is None:
        raise HTTPException(status_code=422, detail="Category not found")


def _get_post_or_404(post_id):
    post = posts.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def _get_category_or_404(category_id):
    category = categories.get(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.get("/", response_model=List[PostList])
async def get_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    category_slug: Optional[str] = None,
):
    category_id = None
    if category_slug:
        category = categories.find_by_unique("slug", category_slug)
        if category is None:
            return []
        category_id = category["id"]
    items = posts.list_published(category_id)[skip : skip + limit]
    return _with_categories(items)


@router.get("/admin", response_model=List[PostSchema])
async def get_all_posts(current_user: dict = Depends(get_current_user)):
    require_admin(current_user, "Not authorized to view all posts")
    return _with_categories(ordering.admin_posts(posts.list_all()))


@router.get("/categories", response_model=List[CategorySchema])
async def get_categories():
    return ordering.categories(categories.list_all())


@router.get("/{slug}", response_model=PostSchema)
async def get_post(slug: str):
    post = posts.find_by_unique("slug", slug)
    if not _published(post):
        raise HTTPException(status_code=404, detail="Post not found")
    return _with_category(post)


@router.get("/category/{category_slug}", response_model=List[PostList])
async def get_posts_by_category(
    category_slug: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    category = categories.find_by_unique("slug", category_slug)
    if category is None:
        return []
    items = posts.list_published(category["id"])[skip : skip + limit]
    return _with_categories(items)


@router.post("/admin", response_model=PostSchema)
async def create_post(post: PostCreate, current_user: dict = Depends(get_current_user)):
    require_admin(current_user, "Not authorized to create posts")
    data = post.model_dump()
    data["slug"] = data.get("slug") or slugify(post.title)
    if posts.find_by_unique("slug", data["slug"]) is not None:
        raise HTTPException(status_code=400, detail=POST_SLUG_TAKEN)
    _require_category(data.get("category_id"))
    data["author_id"] = current_user["id"]
    try:
        created = posts.create(data)
    except UniqueViolation:
        raise HTTPException(status_code=400, detail=POST_SLUG_TAKEN)
    return _with_category(created)


@router.put("/admin/{post_id}", response_model=PostSchema)
async def update_post(
    post_id: int,
    post_update: PostUpdate,
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user, "Not authorized to update posts")
    _get_post_or_404(post_id)
    changes = post_update.model_dump(exclude_unset=True)
    if "category_id" in changes:
        _require_category(changes["category_id"])
    try:
        updated = posts.update(post_id, changes)
    except UniqueViolation:
        raise HTTPException(status_code=400, detail=POST_SLUG_TAKEN)
    return _with_category(updated)


@router.delete("/admin/{post_id}")
async def delete_post(post_id: int, current_user: dict = Depends(get_current_user)):
    require_admin(current_user, "Not authorized to delete posts")
    if not posts.hard_delete(post_id):
        raise HTTPException(status_code=404, detail="Post not found")
    return {"message": "Post deleted successfully"}


@router.post("/admin/{post_id}/publish")
async def publish_post(post_id: int, current_user: dict = Depends(get_current_user)):
    require_admin(current_user, "Not authorized to publish posts")
    post = _get_post_or_404(post_id)
    if _published(post):
        raise HTTPException(status_code=400, detail="Post is already published")
    posts.update(post_id, {"published_at": datetime.now(timezone.utc)})
    return {"message": "Post published successfully"}


@router.post("/categories", response_model=CategorySchema)
async def create_category(
    category: CategoryCreate, current_user: dict = Depends(get_current_user)
):
    require_admin(current_user, "Not authorized to create categories")
    data = category.model_dump()
    data["slug"] = data.get("slug") or slugify(category.name)
    if categories.find_by_unique("slug", data["slug"]) is not None:
        raise HTTPException(status_code=400, detail=CATEGORY_SLUG_TAKEN)
    try:
        return categories.create(data)
    except UniqueViolation:
        raise HTTPException(status_code=400, detail=CATEGORY_SLUG_TAKEN)


@router.put("/categories/{category_id}", response_model=CategorySchema)
async def update_category(
    category_id: int,
    category_update: CategoryUpdate,
    current_user: dict = Depends(get_current_user),
):
    require_admin(current_user, "Not authorized to update categories")
    _get_category_or_404(category_id)
    try:
        return categories.update(
            category_id, category_update.model_dump(exclude_unset=True)
        )
    except UniqueViolation:
        raise HTTPException(status_code=400, detail=CATEGORY_SLUG_TAKEN)


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int, current_user: dict = Depends(get_current_user)
):
    require_admin(current_user, "Not authorized to delete categories")
    _get_category_or_404(category_id)
    if posts.has_posts_in_category(category_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot delete category that has posts. "
                "Please reassign or delete the posts first."
            ),
        )
    categories.hard_delete(category_id)
    return {"message": "Category deleted successfully"}
