"""User admin routes: listing, deactivation cascade, consent revocation."""

import uuid

from fastapi import status

from bundlemcp.api.controllers.management_controller import ManagementController
from bundlemcp.api.pagination import PageProvider
from bundlemcp.providers import UserServiceProvider
from bundlemcp.schemas import ConsentRead, Page, UserRead


class UserController(ManagementController):
    prefix = "/users"
    tags = ("users",)

    def register(self) -> None:
        self.get("", self.list_users)
        self.post("/{user_id}:deactivate", self.deactivate_user)
        self.get("/{user_id}/consents", self.list_consents)
        self.delete(
            "/{user_id}/consents/{consent_id}",
            self.revoke_consent,
            status_code=status.HTTP_204_NO_CONTENT,
        )

    async def list_users(self, service: UserServiceProvider, page: PageProvider) -> Page[UserRead]:
        return await service.list(offset=page.offset, limit=page.limit)

    async def deactivate_user(self, user_id: uuid.UUID, service: UserServiceProvider) -> UserRead:
        return await service.deactivate(user_id)

    async def list_consents(
        self, user_id: uuid.UUID, service: UserServiceProvider
    ) -> list[ConsentRead]:
        return await service.list_consents(user_id)

    async def revoke_consent(
        self, user_id: uuid.UUID, consent_id: uuid.UUID, service: UserServiceProvider
    ) -> None:
        await service.revoke_consent(user_id, consent_id)
