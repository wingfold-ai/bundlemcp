import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyServerRepository(SqlAlchemyRepository[McpServer, McpServerRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, McpServer, McpServerRow)

    async def page(self, *, offset: int, limit: int) -> tuple[int, list[McpServer]]:
        return await super().page(
            offset=offset, limit=limit, order_by=(McpServerRow.created_at, McpServerRow.id)
        )

    async def by_ids(self, ids: Iterable[uuid.UUID]) -> list[McpServer]:
        wanted = list(ids)
        if not wanted:
            return []
        return await self.all(McpServerRow.id.in_(wanted), order_by=(McpServerRow.name,))  # type: ignore[attr-defined]
