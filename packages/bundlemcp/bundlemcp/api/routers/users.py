"""User admin routes: listing, deactivation cascade (ADM-6), consent revocation (OAS-11)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlmodel import func, select

from bundlemcp.api.deps import DbDep, PageDep, ServiceAuthDep
from bundlemcp.api.schemas import Page
from bundlemcp.models import OAuthAccessToken, OAuthConsent, User, utcnow

router = APIRouter(prefix="/users", tags=["users"])


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    display_name: str | None
    is_admin: bool
    is_active: bool


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: str
    endpoint_id: uuid.UUID
    granted_at: object


@router.get("")
async def list_users(db: DbDep, _auth: ServiceAuthDep, page: PageDep) -> Page[UserRead]:
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    rows = (
        await db.execute(
            select(User).order_by(User.created_at, User.id).offset(page.offset).limit(page.limit)
        )
    ).scalars()
    return Page(
        items=[UserRead.model_validate(u) for u in rows],
        total=total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post("/{user_id}:deactivate")
async def deactivate_user(user_id: uuid.UUID, db: DbDep, _auth: ServiceAuthDep) -> UserRead:
    """ADM-6: deactivation revokes tokens, consents, and (implicitly) sessions.

    Admin browser sessions are re-validated against is_active on each request
    (see current_session_user), so revoking is_active logs them out too.
    """
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    user.is_active = False
    await db.execute(
        update(OAuthAccessToken).where(OAuthAccessToken.user_id == user_id).values(revoked=True)
    )
    await db.execute(
        update(OAuthConsent)
        .where(OAuthConsent.user_id == user_id, OAuthConsent.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user)


@router.get("/{user_id}/consents")
async def list_consents(
    user_id: uuid.UUID, db: DbDep, _auth: ServiceAuthDep
) -> list[ConsentRead]:
    rows = (
        await db.execute(
            select(OAuthConsent).where(
                OAuthConsent.user_id == user_id, OAuthConsent.revoked_at.is_(None)
            )
        )
    ).scalars()
    return [ConsentRead.model_validate(c) for c in rows]


@router.delete("/{user_id}/consents/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_consent(
    user_id: uuid.UUID, consent_id: uuid.UUID, db: DbDep, _auth: ServiceAuthDep
) -> None:
    """OAS-11: revoking consent also revokes tokens issued under it."""
    consent = (
        await db.execute(
            select(OAuthConsent).where(
                OAuthConsent.id == consent_id, OAuthConsent.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if consent is None:
        return
    consent.revoked_at = utcnow()
    await db.execute(
        update(OAuthAccessToken)
        .where(
            OAuthAccessToken.user_id == user_id,
            OAuthAccessToken.client_id == consent.client_id,
            OAuthAccessToken.endpoint_id == consent.endpoint_id,
        )
        .values(revoked=True)
    )
    await db.commit()
