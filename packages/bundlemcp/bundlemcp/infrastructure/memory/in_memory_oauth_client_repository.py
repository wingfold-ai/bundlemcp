from datetime import datetime

from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryOAuthClientRepository(InMemoryRepository[OAuthClient]):
    def __init__(self) -> None:
        super().__init__(key=lambda client: client.client_id)

    async def purge_never_used(self, *, created_before: datetime) -> int:
        stale = self.where(lambda c: c.last_used_at is None and c.created_at < created_before)
        for client in stale:
            await self.delete(client)
        return len(stale)
