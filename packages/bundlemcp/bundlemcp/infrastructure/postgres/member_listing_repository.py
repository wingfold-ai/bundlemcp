import uuid
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.member_listing import MemberListing
from bundlemcp.infrastructure.postgres.rows.member_listing_row import MemberListingRow
from bundlemcp.infrastructure.postgres.sqlalchemy_repository import SqlAlchemyRepository


class SqlAlchemyMemberListingRepository(SqlAlchemyRepository[MemberListing, MemberListingRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MemberListing, MemberListingRow)

    async def for_server(self, server_id: uuid.UUID) -> list[MemberListing]:
        return await self.all(MemberListingRow.server_id == server_id)

    async def for_servers(
        self, server_ids: Iterable[uuid.UUID], kind: ListingKind
    ) -> list[MemberListing]:
        ids = list(server_ids)
        if not ids:
            return []
        return await self.all(
            MemberListingRow.server_id.in_(ids),  # type: ignore[attr-defined]
            MemberListingRow.kind == kind,
        )
