"""User admin routes: listing, deactivation cascade, consent revocation.

Thin controllers: HTTP concerns only; business logic lives in UserService.
"""

import uuid

from fastapi import APIRouter, status

from bundlemcp.api.auth import ServiceAuthProvider
from bundlemcp.api.pagination import PageProvider
from bundlemcp.api.providers import UserServiceProvider
from bundlemcp.schemas import ConsentRead, Page, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    service: UserServiceProvider, _auth: ServiceAuthProvider, page: PageProvider
) -> Page[UserRead]:
    return await service.list(offset=page.offset, limit=page.limit)


@router.post("/{user_id}:deactivate")
async def deactivate_user(
    user_id: uuid.UUID, service: UserServiceProvider, _auth: ServiceAuthProvider
) -> UserRead:
    return await service.deactivate(user_id)


@router.get("/{user_id}/consents")
async def list_consents(
    user_id: uuid.UUID, service: UserServiceProvider, _auth: ServiceAuthProvider
) -> list[ConsentRead]:
    return await service.list_consents(user_id)


@router.delete("/{user_id}/consents/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_consent(
    user_id: uuid.UUID,
    consent_id: uuid.UUID,
    service: UserServiceProvider,
    _auth: ServiceAuthProvider,
) -> None:
    await service.revoke_consent(user_id, consent_id)
