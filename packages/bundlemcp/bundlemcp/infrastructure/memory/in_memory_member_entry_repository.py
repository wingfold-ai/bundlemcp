import uuid
from collections.abc import Iterable

from bundlemcp.domain.servers.member_entry import MemberEntry
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryMemberEntryRepository(InMemoryRepository[MemberEntry]):
    async def for_server(self, server_id: uuid.UUID, kind: MemberEntryKind) -> list[MemberEntry]:
        return self.where(lambda e: e.server_id == server_id and e.kind == kind)

    async def for_servers(
        self, server_ids: Iterable[uuid.UUID], kind: MemberEntryKind
    ) -> list[MemberEntry]:
        ids = set(server_ids)
        return self.where(lambda e: e.server_id in ids and e.kind == kind)
