import uuid

from sqlalchemy import select
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

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool:
        changed = await self.update_where(
            UpstreamOAuthClientRow.id == id,
            UpstreamOAuthClientRow.client_secret_encrypted == expected,
            client_secret_encrypted=new,
        )
        return changed == 1

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[UpstreamOAuthClient]:
        statement = select(UpstreamOAuthClientRow).order_by(UpstreamOAuthClientRow.id).limit(limit)
        if after is not None:
            statement = statement.where(UpstreamOAuthClientRow.id > after)
        await self.flush_pending()
        rows = (await self._session.execute(statement)).scalars()
        return [self._to_entity(row) for row in rows]
