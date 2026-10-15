import uuid

from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryUpstreamClientRepository(InMemoryRepository[UpstreamOAuthClient]):
    async def for_server(self, server_id: uuid.UUID) -> UpstreamOAuthClient | None:
        return self.first(lambda c: c.server_id == server_id)

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool:
        client = self.first(lambda c: c.id == id and c.client_secret_encrypted == expected)
        if client is None:
            return False
        client.client_secret_encrypted = new
        return True

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[UpstreamOAuthClient]:
        ordered = sorted(
            self.where(lambda row: after is None or row.id > after), key=lambda row: row.id
        )
        return ordered[:limit]
