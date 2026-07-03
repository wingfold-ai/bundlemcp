"""API key routes.

Thin controllers: HTTP concerns only; business logic lives in ApiKeyService.
"""

import uuid

from fastapi import APIRouter, status

from bundlemcp.api.deps import ApiKeyServiceDep, PageDep, ServiceAuthDep
from bundlemcp.api.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("")
async def list_keys(
    svc: ApiKeyServiceDep, _auth: ServiceAuthDep, page: PageDep
) -> Page[ApiKeyRead]:
    return await svc.list(offset=page.offset, limit=page.limit)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate, svc: ApiKeyServiceDep, _auth: ServiceAuthDep
) -> ApiKeyCreated:
    return await svc.create(body)


@router.post("/{key_id}:deactivate")
async def deactivate_key(
    key_id: uuid.UUID, svc: ApiKeyServiceDep, _auth: ServiceAuthDep
) -> ApiKeyRead:
    return await svc.deactivate(key_id)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(key_id: uuid.UUID, svc: ApiKeyServiceDep, _auth: ServiceAuthDep) -> None:
    await svc.delete(key_id)
