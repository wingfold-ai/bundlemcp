from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryApiKeyRepository(InMemoryRepository[ApiKey]):
    async def by_hash(self, key_hash: str) -> ApiKey | None:
        return self.first(lambda k: k.key_hash == key_hash)

    async def any_of_kind(self, kind: ApiKeyKind) -> ApiKey | None:
        return self.first(lambda k: k.kind == kind)
