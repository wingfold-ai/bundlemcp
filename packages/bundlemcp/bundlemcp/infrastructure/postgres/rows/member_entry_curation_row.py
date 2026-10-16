"""The ``bundle_member_entries`` table, as SQLAlchemy sees it."""

import uuid

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel


class MemberEntryCurationRow(SQLModel, table=True):
    __tablename__ = "bundle_member_entries"
    __table_args__ = (
        UniqueConstraint("bundle_id", "entry_id", name="uq_bundle_member_entries_pair"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the curation"
    )
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True),
        description="Bundle this curation applies to",
    )
    entry_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("member_entries.id", ondelete="CASCADE"), index=True),
        description="Cached member entry being curated",
    )
    enabled: bool = Field(default=True, description="Whether the bundle serves the entry")
    override_title: str | None = Field(default=None, description="Title presented instead")
    override_description: str | None = Field(
        default=None, description="Description presented instead"
    )
