import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyToolRepository(SqlAlchemyRepository[Tool, ToolRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Tool, ToolRow)

    async def for_server(self, server_id: uuid.UUID) -> list[Tool]:
        return await self.all(ToolRow.server_id == server_id, order_by=(ToolRow.name,))

    async def for_servers(self, server_ids: Iterable[uuid.UUID]) -> list[Tool]:
        ids = list(server_ids)
        if not ids:
            return []
        return await self.all(ToolRow.server_id.in_(ids), order_by=(ToolRow.name,))  # type: ignore[attr-defined]

    async def page_for_server(
        self, server_id: uuid.UUID, *, offset: int, limit: int
    ) -> PageSlice[Tool]:
        return await super().page(
            ToolRow.server_id == server_id, offset=offset, limit=limit, order_by=(ToolRow.name,)
        )
