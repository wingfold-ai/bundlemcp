"""User admin routes: listing, deactivation cascade, consent revocation.

Thin controllers: HTTP concerns only; business logic lives in UserService.
"""

import uuid

from fastapi import APIRouter, status

from bundlemcp.api.deps import PageDep, ServiceAuthDep, UserServiceDep
from bundlemcp.api.schemas import ConsentRead, Page, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(svc: UserServiceDep, _auth: ServiceAuthDep, page: PageDep) -> Page[UserRead]:
    return await svc.list(offset=page.offset, limit=page.limit)


@router.post("/{user_id}:deactivate")
async def deactivate_user(
    user_id: uuid.UUID, svc: UserServiceDep, _auth: ServiceAuthDep
) -> UserRead:
    return await svc.deactivate(user_id)


@router.get("/{user_id}/consents")
async def list_consents(
    user_id: uuid.UUID, svc: UserServiceDep, _auth: ServiceAuthDep
) -> list[ConsentRead]:
    return await svc.list_consents(user_id)


@router.delete("/{user_id}/consents/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_consent(
    user_id: uuid.UUID, consent_id: uuid.UUID, svc: UserServiceDep, _auth: ServiceAuthDep
) -> None:
    await svc.revoke_consent(user_id, consent_id)
