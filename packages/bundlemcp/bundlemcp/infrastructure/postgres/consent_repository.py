import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.infrastructure.postgres.rows.oauth_consent_row import OAuthConsentRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyConsentRepository(SqlAlchemyRepository[OAuthConsent, OAuthConsentRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OAuthConsent, OAuthConsentRow)

    async def active(
        self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID
    ) -> OAuthConsent | None:
        return await self.one(
            OAuthConsentRow.user_id == user_id,
            OAuthConsentRow.client_id == client_id,
            OAuthConsentRow.endpoint_id == endpoint_id,
            OAuthConsentRow.revoked_at.is_(None),  # type: ignore[union-attr]
        )

    async def active_for_user(self, user_id: uuid.UUID) -> list[OAuthConsent]:
        return await self.all(
            OAuthConsentRow.user_id == user_id,
            OAuthConsentRow.revoked_at.is_(None),  # type: ignore[union-attr]
        )

    async def find(self, user_id: uuid.UUID, consent_id: uuid.UUID) -> OAuthConsent | None:
        return await self.one(OAuthConsentRow.id == consent_id, OAuthConsentRow.user_id == user_id)

    async def revoke_for_user(self, user_id: uuid.UUID, *, at: datetime) -> None:
        await self.update_where(
            OAuthConsentRow.user_id == user_id,
            OAuthConsentRow.revoked_at.is_(None),  # type: ignore[union-attr]
            revoked_at=at,
        )
