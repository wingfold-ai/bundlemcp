from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyOAuthClientRepository(SqlAlchemyRepository[OAuthClient, OAuthClientRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OAuthClient, OAuthClientRow, key=lambda client: client.client_id)

    async def count_never_used(self) -> int:
        return await self.count(OAuthClientRow.last_used_at.is_(None))  # type: ignore[union-attr]

    async def purge_never_used(self, *, created_before: datetime) -> int:
        return await self.delete_where(
            OAuthClientRow.last_used_at.is_(None),  # type: ignore[union-attr]
            OAuthClientRow.created_at < created_before,
        )
