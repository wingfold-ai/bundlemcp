import uuid

from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryUpstreamTokenRepository(InMemoryRepository[UpstreamOAuthToken]):
    async def find(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        return self.first(lambda t: t.server_id == server_id and t.user_id == user_id)
