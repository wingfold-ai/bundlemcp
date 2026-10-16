"""The ``member_listings`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.domain.servers.listing_kind import ListingKind
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class MemberListingRow(SQLModel, table=True):
    __tablename__ = "member_listings"
    __table_args__ = (
        UniqueConstraint("server_id", "kind", name="uq_member_listings_server_kind"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the listing"
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True),
        description="Server whose listing this is",
    )
    kind: ListingKind = Field(
        sa_type=String, description="'prompts', 'resources' or 'resource_templates'"
    )
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="The entries in wire form, in the server's order",
    )
    cache_scope: str | None = Field(
        default=None, description="'public' or 'private' as the server gave it, if it did"
    )
    complete: bool = Field(default=True, description="False when the listing was cut at the bound")
    listing_hash: str = Field(description="Hash of entries, scope and completeness")
    listed_at: datetime = Field(
        sa_column=timestamp_column(), description="When a change to the listing was last stored"
    )
