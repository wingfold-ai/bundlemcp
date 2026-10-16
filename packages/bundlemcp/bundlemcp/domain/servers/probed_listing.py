from typing import Any, Literal

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.listing_kind import ListingKind


class ProbedListing(BaseModel):
    """One of a server's listings as a probe read it, before it is stored."""

    kind: ListingKind = Field(description="Which list method the listing answers")
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The entries in wire form and in the server's order; empty when incomplete",
    )
    cache_scope: Literal["public", "private"] | None = Field(
        default=None,
        description="'private' if any page was marked private, 'public' if every page was "
        "marked public, None when the server gave no scope",
    )
    complete: bool = Field(
        default=True,
        description="False when the listing was longer than the bound and was not kept",
    )
