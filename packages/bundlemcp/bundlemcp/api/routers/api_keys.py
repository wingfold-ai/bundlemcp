"""API key routes.

Thin controllers: HTTP concerns only; business logic lives in ApiKeyService.
"""

import uuid

from fastapi import APIRouter, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.api.providers import ApiKeyServiceProvider
from bundlemcp.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("")
async def list_keys(
    service: ApiKeyServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[ApiKeyRead]:
    return await service.list(offset=page.offset, limit=page.limit)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate, service: ApiKeyServiceProvider, _auth: ServiceAuthProvider
) -> ApiKeyCreated:
    return await service.create(body)


@router.post("/{key_id}:deactivate")
async def deactivate_key(
    key_id: uuid.UUID, service: ApiKeyServiceProvider, _auth: ServiceAuthProvider
) -> ApiKeyRead:
    return await service.deactivate(key_id)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: uuid.UUID, service: ApiKeyServiceProvider, _auth: ServiceAuthProvider
) -> None:
    await service.delete(key_id)
