import uuid
from collections.abc import Iterable

from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_observations import ServerObservations
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository
from bundlemcp.infrastructure.memory.no_stored_secrets import NoStoredSecrets


class InMemoryServerRepository(InMemoryRepository[McpServer]):
    """Servers in a dict; their static headers are never encrypted, so nothing is ever sealed."""

    async def by_ids(self, ids: Iterable[uuid.UUID]) -> list[McpServer]:
        wanted = set(ids)
        return sorted(self.where(lambda s: s.id in wanted), key=lambda s: s.name)

    async def record_observations(
        self, server_id: uuid.UUID, observations: ServerObservations
    ) -> bool:
        stored = self._rows.get(server_id)
        if stored is None:
            return False
        for field, value in observations:
            setattr(stored, field, value)
        return True

    def header_ciphertexts(self) -> NoStoredSecrets:
        return NoStoredSecrets()

    async def seal_plaintext_headers(self, limit: int) -> int:
        return 0

    async def count_plaintext_headers(self) -> int:
        return len(self.where(lambda s: bool(s.static_headers)))
