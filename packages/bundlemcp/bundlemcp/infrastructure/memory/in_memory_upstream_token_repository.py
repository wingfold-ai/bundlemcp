import uuid

from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryUpstreamTokenRepository(InMemoryRepository[UpstreamOAuthToken]):
    async def find(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        return self.first(lambda t: t.server_id == server_id and t.user_id == user_id)

    async def any_valid_user_connection(self, server_id: uuid.UUID) -> UpstreamOAuthToken | None:
        return self.first(
            lambda t: t.server_id == server_id and t.user_id is not None and t.is_valid
        )

    async def for_server(self, server_id: uuid.UUID) -> list[UpstreamOAuthToken]:
        return self.where(lambda t: t.server_id == server_id)

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        owned = self.where(lambda t: t.user_id == user_id)
        for token in owned:
            await self.delete(token)
        return len(owned)

    async def replace_ciphertext(self, id: uuid.UUID, expected: str, new: str) -> bool:
        token = self.first(lambda t: t.id == id and t.tokens_encrypted == expected)
        if token is None:
            return False
        token.tokens_encrypted = new
        return True

    async def page_after(self, after: uuid.UUID | None, limit: int) -> list[UpstreamOAuthToken]:
        ordered = sorted(
            self.where(lambda row: after is None or row.id > after), key=lambda row: row.id
        )
        return ordered[:limit]
