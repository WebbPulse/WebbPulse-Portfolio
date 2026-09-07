from dataclasses import dataclass
from typing import Callable, List, Type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...core.security import get_current_user, require_admin
from ...db.repository import Repository


@dataclass(frozen=True)
class CrudConfig:
    repository: Repository
    schema: Type[BaseModel]
    list_schema: Type[BaseModel]
    create_schema: Type[BaseModel]
    update_schema: Type[BaseModel]
    resource: str
    not_found: str
    deleted_message: str
    order: Callable[[list], list]
    default_limit: int = 50
    max_limit: int = 100


def build_crud_router(config: CrudConfig, include_list: bool = True) -> APIRouter:
    router = APIRouter()
    repository = config.repository

    def forbidden(verb):
        return f"Not authorized to {verb} {config.resource}"

    if include_list:

        @router.get("/", response_model=List[config.list_schema])
        async def list_items(
            skip: int = Query(0, ge=0),
            limit: int = Query(config.default_limit, ge=1, le=config.max_limit),
        ):
            items = config.order(repository.list_all())
            return items[skip : skip + limit]

    @router.get("/{item_id}", response_model=config.schema)
    async def get_item(item_id: int):
        item = repository.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=config.not_found)
        return item

    @router.post("/", response_model=config.schema)
    async def create_item(
        payload: config.create_schema,
        current_user: dict = Depends(get_current_user),
    ):
        require_admin(current_user, forbidden("create"))
        return repository.create(payload.model_dump())

    @router.put("/{item_id}", response_model=config.schema)
    async def update_item(
        item_id: int,
        payload: config.update_schema,
        current_user: dict = Depends(get_current_user),
    ):
        require_admin(current_user, forbidden("update"))
        item = repository.update(item_id, payload.model_dump(exclude_unset=True))
        if item is None:
            raise HTTPException(status_code=404, detail=config.not_found)
        return item

    @router.delete("/{item_id}")
    async def delete_item(
        item_id: int,
        current_user: dict = Depends(get_current_user),
    ):
        require_admin(current_user, forbidden("delete"))
        if not repository.soft_delete(item_id):
            raise HTTPException(status_code=404, detail=config.not_found)
        return {"message": config.deleted_message}

    return router
