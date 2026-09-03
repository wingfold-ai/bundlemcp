"""API key routes."""

import uuid

from fastapi import status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.providers import ApiKeyServiceProvider
from bundlemcp.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page


class ApiKeyController(ManagementController):
    prefix = "/api-keys"
    tags = ("api-keys",)

    def register(self) -> None:
        self.get("", self.list_keys)
        self.post("", self.create_key, status_code=status.HTTP_201_CREATED)
        self.post("/{key_id}:deactivate", self.deactivate_key)
        self.delete("/{key_id}", self.delete_key, status_code=status.HTTP_204_NO_CONTENT)

    async def list_keys(
        self, service: ApiKeyServiceProvider, page: PageProvider
    ) -> Page[ApiKeyRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    async def create_key(self, body: ApiKeyCreate, service: ApiKeyServiceProvider) -> ApiKeyCreated:
        return await service.create(body)

    async def deactivate_key(self, key_id: uuid.UUID, service: ApiKeyServiceProvider) -> ApiKeyRead:
        return await service.deactivate(key_id)

    async def delete_key(self, key_id: uuid.UUID, service: ApiKeyServiceProvider) -> None:
        await service.delete(key_id)
