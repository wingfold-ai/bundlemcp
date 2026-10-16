"""Reading members' stored listings while serving a list method."""

import uuid
from typing import Any

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.mcp_server import McpServer


class MemberListingReader:
    """The listings discovery stored that may be served in place of asking a member.

    Only the three list methods read here, in a unit of work of their own, so
    no other request pays for it.
    """

    def __init__(self, units: UnitOfWorkFactory) -> None:
        self._units = units

    async def shareable(
        self, servers: list[McpServer], kind: ListingKind
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        """The entries of each server's shareable listing of ``kind``, by server id.

        A server missing from the answer has no listing every caller may be
        shown, and is asked live.
        """
        if not servers:
            return {}
        by_id = {server.id: server for server in servers}
        async with self._units.open() as uow:
            listings = await uow.member_listings.for_servers(by_id, kind)
        return {
            listing.server_id: listing.entries
            for listing in listings
            if listing.shareable_for(by_id[listing.server_id])
        }
