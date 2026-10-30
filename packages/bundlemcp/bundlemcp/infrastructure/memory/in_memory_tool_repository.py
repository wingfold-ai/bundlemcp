import uuid
from collections.abc import Iterable

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.application.contracts.persistence.store_conflict import StoreConflict
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryToolRepository(InMemoryRepository[Tool]):
    """Tools in a dict, holding the store's rule that a server lists a tool name once."""

    def add(self, entity: Tool) -> Tool:
        twin = self.first(
            lambda t: (
                t.server_id == entity.server_id and t.name == entity.name and t.id != entity.id
            )
        )
        if twin is not None:
            raise StoreConflict("uq_tools_server_name")
        return super().add(entity)

    async def for_server(self, server_id: uuid.UUID) -> list[Tool]:
        return sorted(self.where(lambda t: t.server_id == server_id), key=lambda t: t.name)

    async def for_servers(self, server_ids: Iterable[uuid.UUID]) -> list[Tool]:
        ids = set(server_ids)
        return sorted(self.where(lambda t: t.server_id in ids), key=lambda t: t.name)

    async def page_for_server(
        self, server_id: uuid.UUID, *, offset: int, limit: int
    ) -> PageSlice[Tool]:
        return self._page(
            self.where(lambda t: t.server_id == server_id),
            offset=offset,
            limit=limit,
            order=lambda t: t.name,
        )
