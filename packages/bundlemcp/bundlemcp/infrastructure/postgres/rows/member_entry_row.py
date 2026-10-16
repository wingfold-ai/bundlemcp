"""The ``member_entries`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.domain.servers.member_entry_kind import MemberEntryKind
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class MemberEntryRow(SQLModel, table=True):
    __tablename__ = "member_entries"
    __table_args__ = (
        UniqueConstraint("server_id", "kind", "key", name="uq_member_entries_server_kind_key"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the entry"
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True),
        description="Server that lists the entry",
    )
    kind: MemberEntryKind = Field(sa_type=String, description="'prompt' or 'resource'")
    key: str = Field(description="The prompt's name, or the resource's URI")
    name: str = Field(description="Its listed name")
    title: str | None = Field(default=None, description="Title the server reports")
    description: str | None = Field(default=None, description="Description the server reports")
    entry_hash: str = Field(description="Hash of what is cached")
    stale_since: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(nullable=True),
        description="When discovery first stopped listing the entry; None while listed",
    )
