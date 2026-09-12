"""A generic CRUD router the five resume collections are each built from.

One configuration object per collection supplies the repository, the schemas,
the ordering and the message wording, so the five differ only in data."""

import inspect
from dataclasses import dataclass
from typing import Callable, List, Type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...core.security import CurrentUser, require_admin
from ...db.repository import Repository


@dataclass(frozen=True)
class CrudConfig:
    """Everything one resume collection's CRUD router needs to differ by."""

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


def _annotate_body(endpoint: Callable, parameter: str, model: Type[BaseModel]) -> None:
    """Point one parameter's annotation at a model chosen at runtime.

    FastAPI reads the signature to build the request body, and the concrete model
    is only known here, so the annotation is set on the signature rather than
    written as a static type the checker would have to accept a variable in.
    """
    signature = inspect.signature(endpoint)
    parameters = [
        value.replace(annotation=model) if name == parameter else value for name, value in signature.parameters.items()
    ]
    endpoint.__signature__ = signature.replace(parameters=parameters)


def build_crud_router(config: CrudConfig, include_list: bool = True) -> APIRouter:
    """Build the list, read, create, update and delete routes for one collection."""
    router = APIRouter()
    repository = config.repository

    def forbidden(verb):
        """The authorization failure message for one verb on this resource."""
        return f"Not authorized to {verb} {config.resource}"

    if include_list:

        @router.get("/", response_model=List[config.list_schema])
        async def list_items(
            skip: int = Query(0, ge=0),
            limit: int = Query(config.default_limit, ge=1, le=config.max_limit),
        ):
            """A page of this collection in its configured order."""
            items = config.order(repository.list_all())
            return items[skip : skip + limit]

    @router.get("/{item_id}", response_model=config.schema)
    async def get_item(item_id: int):
        """One item by id, or a 404."""
        item = repository.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=config.not_found)
        return item

    async def create_item(
        payload: BaseModel,
        current_user: dict = Depends(CurrentUser),
    ):
        """Create one item. Admin only."""
        require_admin(current_user, forbidden("create"))
        return repository.create(payload.model_dump())

    _annotate_body(create_item, "payload", config.create_schema)
    router.post("/", response_model=config.schema)(create_item)

    async def update_item(
        item_id: int,
        payload: BaseModel,
        current_user: dict = Depends(CurrentUser),
    ):
        """Apply a partial edit to one item. Admin only."""
        require_admin(current_user, forbidden("update"))
        item = repository.update(item_id, payload.model_dump(exclude_unset=True))
        if item is None:
            raise HTTPException(status_code=404, detail=config.not_found)
        return item

    _annotate_body(update_item, "payload", config.update_schema)
    router.put("/{item_id}", response_model=config.schema)(update_item)

    @router.delete("/{item_id}")
    async def delete_item(
        item_id: int,
        current_user: dict = Depends(CurrentUser),
    ):
        """Soft delete one item. Admin only."""
        require_admin(current_user, forbidden("delete"))
        if not repository.soft_delete(item_id):
            raise HTTPException(status_code=404, detail=config.not_found)
        return {"message": config.deleted_message}

    return router
