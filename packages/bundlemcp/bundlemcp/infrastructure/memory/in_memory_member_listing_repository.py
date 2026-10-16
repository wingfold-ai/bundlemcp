import uuid
from collections.abc import Iterable

from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.member_listing import MemberListing
from bundlemcp.infrastructure.memory.in_memory_repository import InMemoryRepository


class InMemoryMemberListingRepository(InMemoryRepository[MemberListing]):
    async def for_server(self, server_id: uuid.UUID) -> list[MemberListing]:
        return self.where(lambda listing: listing.server_id == server_id)

    async def for_servers(
        self, server_ids: Iterable[uuid.UUID], kind: ListingKind
    ) -> list[MemberListing]:
        ids = set(server_ids)
        return self.where(lambda listing: listing.server_id in ids and listing.kind == kind)
