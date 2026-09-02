"""User admin business logic: listing, deactivation cascade, consent management."""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.models import OAuthAccessToken, OAuthConsent, User, utcnow
from bundlemcp.schemas import ConsentRead, Page, UserRead
from bundlemcp.services.errors import NotFoundError


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list(self, *, offset: int, limit: int) -> Page[UserRead]:
        total = (await self._db.execute(select(func.count()).select_from(User))).scalar_one()
        rows = (
            await self._db.execute(
                select(User).order_by(User.created_at, User.id).offset(offset).limit(limit)
            )
        ).scalars()
        return Page(
            items=[UserRead.model_validate(u) for u in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def deactivate(self, user_id: uuid.UUID) -> UserRead:
        """Deactivation revokes tokens, consents, and (implicitly) sessions.

        Admin browser sessions are re-validated against is_active on each request
        (see current_session_user), so revoking is_active logs them out too.
        """
        user = (await self._db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user is None:
            raise NotFoundError("user not found")
        user.is_active = False
        await self._db.execute(
            update(OAuthAccessToken).where(OAuthAccessToken.user_id == user_id).values(revoked=True)
        )
        await self._db.execute(
            update(OAuthConsent)
            .where(OAuthConsent.user_id == user_id, OAuthConsent.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await self._db.commit()
        await self._db.refresh(user)
        return UserRead.model_validate(user)

    async def list_consents(self, user_id: uuid.UUID) -> list[ConsentRead]:
        rows = (
            await self._db.execute(
                select(OAuthConsent).where(
                    OAuthConsent.user_id == user_id, OAuthConsent.revoked_at.is_(None)
                )
            )
        ).scalars()
        return [ConsentRead.model_validate(c) for c in rows]

    async def revoke_consent(self, user_id: uuid.UUID, consent_id: uuid.UUID) -> None:
        """Revoking a consent also revokes the tokens issued under it."""
        consent = (
            await self._db.execute(
                select(OAuthConsent).where(
                    OAuthConsent.id == consent_id, OAuthConsent.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if consent is None:
            return
        consent.revoked_at = utcnow()
        await self._db.execute(
            update(OAuthAccessToken)
            .where(
                OAuthAccessToken.user_id == user_id,
                OAuthAccessToken.client_id == consent.client_id,
                OAuthAccessToken.endpoint_id == consent.endpoint_id,
            )
            .values(revoked=True)
        )
        await self._db.commit()
