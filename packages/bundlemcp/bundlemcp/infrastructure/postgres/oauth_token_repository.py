import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken
from bundlemcp.infrastructure.postgres.rows.oauth_access_token_row import OAuthAccessTokenRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyOAuthTokenRepository(SqlAlchemyRepository[OAuthAccessToken, OAuthAccessTokenRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OAuthAccessToken, OAuthAccessTokenRow)

    async def by_access_hash(self, digest: str) -> OAuthAccessToken | None:
        return await self.one(OAuthAccessTokenRow.access_token_hash == digest)

    async def by_refresh_hash(self, digest: str) -> OAuthAccessToken | None:
        return await self.one(OAuthAccessTokenRow.refresh_token_hash == digest)

    async def by_either_hash(self, digest: str) -> OAuthAccessToken | None:
        return await self.one(
            (OAuthAccessTokenRow.access_token_hash == digest)
            | (OAuthAccessTokenRow.refresh_token_hash == digest)
        )

    async def revoke_unless_revoked(self, token_id: uuid.UUID) -> bool:
        rotated = await self.update_where(
            OAuthAccessTokenRow.id == token_id,
            OAuthAccessTokenRow.revoked.is_(False),  # type: ignore[union-attr]
            revoked=True,
        )
        return rotated == 1

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        await self.update_where(OAuthAccessTokenRow.family_id == family_id, revoked=True)

    async def revoke_for_user(self, user_id: uuid.UUID) -> None:
        await self.update_where(OAuthAccessTokenRow.user_id == user_id, revoked=True)

    async def revoke_for_consent(
        self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID
    ) -> None:
        await self.update_where(
            OAuthAccessTokenRow.user_id == user_id,
            OAuthAccessTokenRow.client_id == client_id,
            OAuthAccessTokenRow.endpoint_id == endpoint_id,
            revoked=True,
        )

    async def purge_expired(self, *, refresh_expired_before: datetime) -> int:
        return await self.delete_where(
            OAuthAccessTokenRow.refresh_expires_at < refresh_expired_before
        )
