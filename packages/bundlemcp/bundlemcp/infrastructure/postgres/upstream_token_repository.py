import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_token_row import UpstreamOAuthTokenRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyUpstreamTokenRepository(
    SqlAlchemyRepository[UpstreamOAuthToken, UpstreamOAuthTokenRow]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UpstreamOAuthToken, UpstreamOAuthTokenRow)

    async def find(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        user_clause = (
            UpstreamOAuthTokenRow.user_id.is_(None)  # type: ignore[union-attr]
            if user_id is None
            else UpstreamOAuthTokenRow.user_id == user_id
        )
        return await self.one(UpstreamOAuthTokenRow.server_id == server_id, user_clause)

    async def any_valid_user_connection(self, server_id: uuid.UUID) -> UpstreamOAuthToken | None:
        rows = await self.all(
            UpstreamOAuthTokenRow.server_id == server_id,
            UpstreamOAuthTokenRow.user_id.is_not(None),  # type: ignore[union-attr]
            UpstreamOAuthTokenRow.is_valid.is_(True),  # type: ignore[attr-defined]
        )
        return rows[0] if rows else None

    async def for_server(self, server_id: uuid.UUID) -> list[UpstreamOAuthToken]:
        return await self.all(UpstreamOAuthTokenRow.server_id == server_id)
