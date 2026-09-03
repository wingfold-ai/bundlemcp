"""User admin routes: listing, deactivation cascade, consent revocation."""

import uuid

from fastapi import status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.http import route
from bundlemcp.providers import UserServiceProvider
from bundlemcp.schemas import ConsentRead, Page, UserRead


class UserController(ManagementController):
    prefix = "/users"
    tags = ("users",)

    @route.get("")
    async def list_users(self, service: UserServiceProvider, page: PageProvider) -> Page[UserRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    @route.post("/{user_id}:deactivate")
    async def deactivate_user(self, user_id: uuid.UUID, service: UserServiceProvider) -> UserRead:
        return await service.deactivate(user_id)

    @route.get("/{user_id}/consents")
    async def list_consents(
        self, user_id: uuid.UUID, service: UserServiceProvider
    ) -> list[ConsentRead]:
        return await service.list_consents(user_id)

    @route.delete("/{user_id}/consents/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def revoke_consent(
        self, user_id: uuid.UUID, consent_id: uuid.UUID, service: UserServiceProvider
    ) -> None:
        await service.revoke_consent(user_id, consent_id)
