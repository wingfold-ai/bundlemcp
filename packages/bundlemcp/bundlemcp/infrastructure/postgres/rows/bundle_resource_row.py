"""The ``bundle_resources`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.domain.bundles.resource_mime_type import ResourceMimeType
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class BundleResourceRow(SQLModel, table=True):
    __tablename__ = "bundle_resources"
    __table_args__ = (UniqueConstraint("bundle_id", "name", name="uq_bundle_resources_name"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the resource"
    )
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True, nullable=False),
        description="Bundle the resource belongs to",
    )
    name: str = Field(description="Resource name, unique in its bundle")  # BND-23
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(default=None, description="What the resource contains")
    mime_type: ResourceMimeType = Field(
        default=ResourceMimeType.MARKDOWN, sa_type=String, description="Text format of the content"
    )
    # Stored beside the content so a listing never has to read the content to size it.
    size_bytes: int = Field(default=0, description="Size of the content, in UTF-8 bytes")
    content: str = Field(sa_column=Column(Text, nullable=False), description="The document itself")
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=timestamp_column(), description="When it was created"
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(onupdate=utcnow),
        description="When it last changed",
    )
