from datetime import datetime

from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryAuthorizationCodeRepository(InMemoryRepository[OAuthAuthorizationCode]):
    def __init__(self) -> None:
        super().__init__(key=lambda code: code.code_hash)

    async def burn(self, code_hash: str) -> bool:
        code = await self.get(code_hash)
        if code is None or code.used:
            return False
        code.used = True
        return True

    async def purge_expired(self, *, expired_before: datetime) -> int:
        stale = self.where(lambda c: c.expires_at < expired_before)
        for code in stale:
            await self.delete(code)
        return len(stale)
