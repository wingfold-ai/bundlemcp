"""User admin business logic: listing, deactivation cascade, consent management."""

from __future__ import annotations

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import NotFoundError
from bundlemcp.application.schemas import ConsentRead, Page, UserRead
from bundlemcp.domain.shared.clock import utcnow


class UserService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list(self, *, offset: int, limit: int) -> Page[UserRead]:
        total, rows = await self._uow.users.page(offset=offset, limit=limit)
        return Page.of(rows, total, offset=offset, limit=limit, read=UserRead.from_entity)

    async def deactivate(self, user_id: uuid.UUID) -> UserRead:
        """Deactivation revokes tokens, consents, and (implicitly) sessions.

        Admin browser sessions are re-validated against is_active on each request,
        so revoking is_active logs them out too.
        """
        user = await self._uow.users.get(user_id)
        if user is None:
            raise NotFoundError("user not found")
        user.is_active = False
        self._uow.users.add(user)
        await self._uow.oauth_tokens.revoke_for_user(user_id)
        await self._uow.consents.revoke_for_user(user_id, at=utcnow())
        await self._uow.commit()
        await self._uow.refresh(user)
        return UserRead.from_entity(user)

    async def list_consents(self, user_id: uuid.UUID) -> list[ConsentRead]:
        rows = await self._uow.consents.active_for_user(user_id)
        return [ConsentRead.from_entity(c) for c in rows]

    async def revoke_consent(self, user_id: uuid.UUID, consent_id: uuid.UUID) -> None:
        """Revoking a consent also revokes the tokens issued under it."""
        consent = await self._uow.consents.find(user_id, consent_id)
        if consent is None:
            return
        consent.revoked_at = utcnow()
        self._uow.consents.add(consent)
        await self._uow.oauth_tokens.revoke_for_consent(
            user_id, consent.client_id, consent.endpoint_id
        )
        await self._uow.commit()
