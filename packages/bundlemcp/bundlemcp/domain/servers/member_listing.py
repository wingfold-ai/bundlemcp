import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.domain.servers.listing_snapshot_mode import ListingSnapshotMode
from bundlemcp.domain.servers.mcp_server import McpServer


class MemberListing(BaseModel):
    """A member's prompt, resource or resource-template listing as its last discovery read it.

    Endpoints answer the list methods from it instead of asking the member, as
    long as every caller may be shown the same listing.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the listing")
    server_id: uuid.UUID = Field(description="Server whose listing this is")
    kind: ListingKind = Field(description="Which list method the listing answers")
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The entries in wire form, exactly as and in the order the server listed them",
    )
    cache_scope: Literal["public", "private"] | None = Field(
        default=None,
        description="The cache scope the server put on the wire for the listing; None when it "
        "sent none",
    )
    complete: bool = Field(
        default=True,
        description="False when the listing was longer than the bound, so it is never served",
    )
    listing_hash: str = Field(
        description="Hash of entries, scope and completeness, so an unchanged listing costs no "
        "write on re-probe"
    )
    listed_at: datetime = Field(description="When discovery last stored a change to the listing")

    def shareable_for(self, server: McpServer) -> bool:
        """Every caller may be served this listing in place of asking the server.

        The server's setting comes first: ``live`` never shares and ``shared``
        always does, since an SDK may mark every result private by default.
        Under ``auto`` the server's own scope decides when it gave one. Without
        one, the listing is shared only if nothing the server is sent depends on
        the caller, so it could not have listed differently for someone else.
        """
        if not self.complete or server.listing_snapshot is ListingSnapshotMode.LIVE:
            return False
        if server.listing_snapshot is ListingSnapshotMode.SHARED:
            return True
        if self.cache_scope is not None:
            return self.cache_scope == "public"
        return server.is_identity_free
