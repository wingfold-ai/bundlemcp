"""API key routes."""

import uuid

from fastapi import status

from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import ApiKeyServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page


class ApiKeyController(ManagementController):
    prefix = "/api-keys"
    tags = ("api-keys",)

    @route.get("")
    async def list_keys(
        self, service: ApiKeyServiceProvider, page: PageProvider
    ) -> Page[ApiKeyRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.post("", status_code=status.HTTP_201_CREATED)
    async def create_key(self, body: ApiKeyCreate, service: ApiKeyServiceProvider) -> ApiKeyCreated:
        return await service.create(body)

    @route.post("/{key_id}:deactivate")
    async def deactivate_key(self, key_id: uuid.UUID, service: ApiKeyServiceProvider) -> ApiKeyRead:
        return await service.deactivate(key_id)

    @route.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_key(self, key_id: uuid.UUID, service: ApiKeyServiceProvider) -> None:
        await service.delete(key_id)
