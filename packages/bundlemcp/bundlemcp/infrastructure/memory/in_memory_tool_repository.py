import uuid
from collections.abc import Iterable

from bundlemcp.application.contracts.persistence.page_slice import PageSlice
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryToolRepository(InMemoryRepository[Tool]):
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
