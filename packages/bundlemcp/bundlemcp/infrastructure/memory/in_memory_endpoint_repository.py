import uuid

from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryEndpointRepository(InMemoryRepository[Endpoint]):
    async def for_bundle(self, bundle_id: uuid.UUID) -> list[Endpoint]:
        return self.where(lambda e: e.bundle_id == bundle_id)
