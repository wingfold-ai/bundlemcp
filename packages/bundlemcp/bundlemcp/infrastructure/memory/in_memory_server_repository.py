import uuid
from collections.abc import Iterable

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryServerRepository(InMemoryRepository[McpServer]):
    async def by_ids(self, ids: Iterable[uuid.UUID]) -> list[McpServer]:
        wanted = set(ids)
        return sorted(self.where(lambda s: s.id in wanted), key=lambda s: s.name)
