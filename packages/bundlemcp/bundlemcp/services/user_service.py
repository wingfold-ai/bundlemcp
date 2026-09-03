"""User admin business logic: listing, deactivation cascade, consent management."""

from __future__ import annotations

import uuid

from sqlalchemy import update

from bundlemcp.models import OAuthAccessToken, OAuthConsent, User, utcnow
from bundlemcp.schemas import ConsentRead, Page, UserRead
from bundlemcp.services.errors import NotFoundError
from bundlemcp.store import Repository, UnitOfWork


class UserService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow
        self._users = Repository(uow.session, User)
        self._consents = Repository(uow.session, OAuthConsent)

    async def list(self, *, offset: int, limit: int) -> Page[UserRead]:
        total, rows = await self._users.page(
            offset=offset, limit=limit, order_by=(User.created_at, User.id)
        )
        return Page(
            items=[UserRead.from_entity(u) for u in rows], total=total, offset=offset, limit=limit
        )

    async def deactivate(self, user_id: uuid.UUID) -> UserRead:
        """Deactivation revokes tokens, consents, and (implicitly) sessions.

        Admin browser sessions are re-validated against is_active on each request,
        so revoking is_active logs them out too.
        """
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("user not found")
        user.is_active = False
        await self._uow.session.execute(
            update(OAuthAccessToken).where(OAuthAccessToken.user_id == user_id).values(revoked=True)
        )
        await self._uow.session.execute(
            update(OAuthConsent)
            .where(OAuthConsent.user_id == user_id, OAuthConsent.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await self._uow.commit()
        await self._uow.session.refresh(user)
        return UserRead.from_entity(user)

    async def list_consents(self, user_id: uuid.UUID) -> list[ConsentRead]:
        rows = await self._consents.all(
            OAuthConsent.user_id == user_id, OAuthConsent.revoked_at.is_(None)
        )
        return [ConsentRead.from_entity(c) for c in rows]

    async def revoke_consent(self, user_id: uuid.UUID, consent_id: uuid.UUID) -> None:
        """Revoking a consent also revokes the tokens issued under it."""
        consent = await self._consents.one(
            OAuthConsent.id == consent_id, OAuthConsent.user_id == user_id
        )
        if consent is None:
            return
        consent.revoked_at = utcnow()
        await self._uow.session.execute(
            update(OAuthAccessToken)
            .where(
                OAuthAccessToken.user_id == user_id,
                OAuthAccessToken.client_id == consent.client_id,
                OAuthAccessToken.endpoint_id == consent.endpoint_id,
            )
            .values(revoked=True)
        )
        await self._uow.commit()
