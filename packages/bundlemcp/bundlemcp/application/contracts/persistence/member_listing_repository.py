import uuid
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.repository import Repository
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.member_listing import MemberListing


@runtime_checkable
class MemberListingRepository(Repository[MemberListing], Protocol):
    """Members' prompt, resource and resource-template listings as discovery last read them."""

    async def for_server(self, server_id: uuid.UUID) -> list[MemberListing]:
        """Every stored listing of one server, one per kind at most."""
        ...

    async def for_servers(
        self, server_ids: Iterable[uuid.UUID], kind: ListingKind
    ) -> list[MemberListing]:
        """The stored listings of one kind of several servers."""
        ...
