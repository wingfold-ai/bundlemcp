import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyUpstreamClientRepository(
    SqlAlchemyRepository[UpstreamOAuthClient, UpstreamOAuthClientRow]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UpstreamOAuthClient, UpstreamOAuthClientRow)

    async def for_server(self, server_id: uuid.UUID) -> UpstreamOAuthClient | None:
        return await self.one(UpstreamOAuthClientRow.server_id == server_id)
