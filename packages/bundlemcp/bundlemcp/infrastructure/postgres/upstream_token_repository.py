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
