from bundlemcp.domain.access.user import User
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryUserRepository(InMemoryRepository[User]):
    async def by_subject(self, issuer: str, sub: str) -> User | None:
        return self.first(lambda u: u.oidc_issuer == issuer and u.oidc_sub == sub)
