import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.servers.member_entry import MemberEntry
from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.infrastructure.postgres.rows.member_entry_row import MemberEntryRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyMemberEntryRepository(SqlAlchemyRepository[MemberEntry, MemberEntryRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MemberEntry, MemberEntryRow)

    async def for_server(self, server_id: uuid.UUID, kind: MemberEntryKind) -> list[MemberEntry]:
        return await self.all(MemberEntryRow.server_id == server_id, MemberEntryRow.kind == kind)

    async def for_servers(
        self, server_ids: Iterable[uuid.UUID], kind: MemberEntryKind
    ) -> list[MemberEntry]:
        ids = list(server_ids)
        if not ids:
            return []
        return await self.all(
            MemberEntryRow.server_id.in_(ids),  # type: ignore[attr-defined]
            MemberEntryRow.kind == kind,
        )
