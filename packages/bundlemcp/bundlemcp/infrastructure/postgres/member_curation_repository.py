import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration
from bundlemcp.infrastructure.postgres.rows.member_entry_curation_row import (
    MemberEntryCurationRow,
)
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyMemberCurationRepository(
    SqlAlchemyRepository[MemberEntryCuration, MemberEntryCurationRow]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MemberEntryCuration, MemberEntryCurationRow)

    async def for_bundle(self, bundle_id: uuid.UUID) -> list[MemberEntryCuration]:
        return await self.all(MemberEntryCurationRow.bundle_id == bundle_id)

    async def find(self, bundle_id: uuid.UUID, entry_id: uuid.UUID) -> MemberEntryCuration | None:
        return await self.one(
            MemberEntryCurationRow.bundle_id == bundle_id,
            MemberEntryCurationRow.entry_id == entry_id,
        )
