import uuid

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryCurationRepository(InMemoryRepository[BundleTool]):
    async def for_bundle(self, bundle_id: uuid.UUID) -> list[BundleTool]:
        return self.where(lambda c: c.bundle_id == bundle_id)

    async def find(self, bundle_id: uuid.UUID, tool_id: uuid.UUID) -> BundleTool | None:
        return self.first(lambda c: c.bundle_id == bundle_id and c.tool_id == tool_id)

    async def override_name_taken(
        self, bundle_id: uuid.UUID, override_name: str, *, except_tool_id: uuid.UUID
    ) -> bool:
        return (
            self.first(
                lambda c: c.bundle_id == bundle_id
                and c.override_name == override_name
                and c.tool_id != except_tool_id
            )
            is not None
        )
