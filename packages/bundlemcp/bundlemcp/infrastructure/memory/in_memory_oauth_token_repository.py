import uuid
from datetime import datetime

from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryOAuthTokenRepository(InMemoryRepository[OAuthAccessToken]):
    async def by_access_hash(self, digest: str) -> OAuthAccessToken | None:
        return self.first(lambda t: t.access_token_hash == digest)

    async def by_refresh_hash(self, digest: str) -> OAuthAccessToken | None:
        return self.first(lambda t: t.refresh_token_hash == digest)

    async def by_either_hash(self, digest: str) -> OAuthAccessToken | None:
        return self.first(
            lambda t: t.access_token_hash == digest or t.refresh_token_hash == digest
        )

    async def revoke_unless_revoked(self, token_id: uuid.UUID) -> bool:
        token = await self.get(token_id)
        if token is None or token.revoked:
            return False
        token.revoked = True
        return True

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        for token in self.where(lambda t: t.family_id == family_id):
            token.revoked = True

    async def revoke_for_user(self, user_id: uuid.UUID) -> None:
        for token in self.where(lambda t: t.user_id == user_id):
            token.revoked = True

    async def revoke_for_consent(
        self, user_id: uuid.UUID, client_id: str, endpoint_id: uuid.UUID
    ) -> None:
        for token in self.where(
            lambda t: t.user_id == user_id
            and t.client_id == client_id
            and t.endpoint_id == endpoint_id
        ):
            token.revoked = True

    async def purge_expired(self, *, refresh_expired_before: datetime) -> int:
        stale = self.where(
            lambda t: t.refresh_expires_at is not None
            and t.refresh_expires_at < refresh_expired_before
        )
        for token in stale:
            await self.delete(token)
        return len(stale)
