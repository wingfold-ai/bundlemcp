import uuid

from bundlemcp.domain.bundles.bundle_server import BundleServer
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryMembershipRepository(InMemoryRepository[BundleServer]):
    async def for_bundle(self, bundle_id: uuid.UUID) -> list[BundleServer]:
        return self.where(lambda m: m.bundle_id == bundle_id)

    async def for_server(self, server_id: uuid.UUID) -> list[BundleServer]:
        return self.where(lambda m: m.server_id == server_id)

    async def find(self, bundle_id: uuid.UUID, server_id: uuid.UUID) -> BundleServer | None:
        return self.first(lambda m: m.bundle_id == bundle_id and m.server_id == server_id)
