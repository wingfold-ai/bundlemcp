"""The ``bundle_tools`` table, as SQLAlchemy sees it."""

import uuid
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel


class BundleToolRow(SQLModel, table=True):
    __tablename__ = "bundle_tools"
    __table_args__ = (UniqueConstraint("bundle_id", "tool_id", name="uq_bundle_tools_pair"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the curation"
    )
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True),
        description="Bundle this curation applies to",
    )
    tool_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tools.id", ondelete="CASCADE"), index=True),
        description="Tool being curated",
    )
    enabled: bool = Field(  # TM-1
        default=True, description="Whether the tool is served through this bundle"
    )
    override_name: str | None = Field(  # TM-3
        default=None, description="Replacement name clients see instead of 'server__tool'"
    )
    override_title: str | None = Field(
        default=None, description="Replacement display title for this bundle"
    )
    override_description: str | None = Field(
        default=None, description="Replacement description for this bundle"
    )
    override_annotations: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Replacement MCP annotations for this bundle",
    )
