import uuid

from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryMemberCurationRepository(InMemoryRepository[MemberEntryCuration]):
    async def for_bundle(self, bundle_id: uuid.UUID) -> list[MemberEntryCuration]:
        return self.where(lambda c: c.bundle_id == bundle_id)

    async def find(self, bundle_id: uuid.UUID, entry_id: uuid.UUID) -> MemberEntryCuration | None:
        return self.first(lambda c: c.bundle_id == bundle_id and c.entry_id == entry_id)
