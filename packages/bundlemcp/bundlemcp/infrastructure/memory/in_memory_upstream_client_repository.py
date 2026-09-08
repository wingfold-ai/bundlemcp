import uuid

from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryUpstreamClientRepository(InMemoryRepository[UpstreamOAuthClient]):
    async def for_server(self, server_id: uuid.UUID) -> UpstreamOAuthClient | None:
        return self.first(lambda c: c.server_id == server_id)
