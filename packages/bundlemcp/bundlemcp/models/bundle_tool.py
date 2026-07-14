import uuid
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel


class BundleTool(SQLModel, table=True):
    __tablename__ = "bundle_tools"
    __table_args__ = (UniqueConstraint("bundle_id", "tool_id", name="uq_bundle_tools_pair"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    )
    tool_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    )
    enabled: bool = Field(default=True)  # TM-1
    override_name: str | None = None  # TM-3
    override_title: str | None = None
    override_description: str | None = None
    override_annotations: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
