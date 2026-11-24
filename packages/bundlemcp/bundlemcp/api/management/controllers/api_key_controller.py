"""API key routes."""

import uuid

from fastapi import status

from bundlemcp.api.http.management_auth import PrincipalProvider
from bundlemcp.api.http.pagination import PageProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import ApiKeyServiceProvider
from bundlemcp.api.management.controllers.management_controller import ManagementController
from bundlemcp.application.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page
from bundlemcp.domain.access.api_key_scope import ApiKeyScope


class ApiKeyController(ManagementController):
    prefix = "/api-keys"
    tags = ("api-keys",)

    @route.get("", access=ApiKeyScope.READ)
    async def list_keys(
        self, service: ApiKeyServiceProvider, page: PageProvider
    ) -> Page[ApiKeyRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.post("", status_code=status.HTTP_201_CREATED, access=ApiKeyScope.KEYS_MANAGE)
    async def create_key(
        self, body: ApiKeyCreate, service: ApiKeyServiceProvider, principal: PrincipalProvider
    ) -> ApiKeyCreated:
        return await service.create(body, principal)

    @route.post("/{key_id}:deactivate", access=ApiKeyScope.KEYS_MANAGE)
    async def deactivate_key(
        self, key_id: uuid.UUID, service: ApiKeyServiceProvider, principal: PrincipalProvider
    ) -> ApiKeyRead:
        return await service.deactivate(key_id, principal)

    @route.post("/{key_id}:activate", access=ApiKeyScope.KEYS_MANAGE)
    async def activate_key(
        self, key_id: uuid.UUID, service: ApiKeyServiceProvider, principal: PrincipalProvider
    ) -> ApiKeyRead:
        return await service.activate(key_id, principal)

    @route.delete(
        "/{key_id}", status_code=status.HTTP_204_NO_CONTENT, access=ApiKeyScope.KEYS_MANAGE
    )
    async def delete_key(
        self, key_id: uuid.UUID, service: ApiKeyServiceProvider, principal: PrincipalProvider
    ) -> None:
        await service.delete(key_id, principal)
