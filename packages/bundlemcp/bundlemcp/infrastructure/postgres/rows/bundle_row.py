"""The ``bundles`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class BundleRow(SQLModel, table=True):
    __tablename__ = "bundles"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the bundle"
    )
    name: str = Field(unique=True, index=True, description="Unique bundle name")
    description: str | None = Field(  # BND-1
        default=None,
        description="Free-text note about the bundle, served to clients as MCP instructions",
    )
    overview: str | None = Field(  # BND-11
        default=None,
        description="Long-form description of the bundle for people browsing the "
        "catalogue: what it is for, what the tools can do, and anything a user must set "
        "up first. Plain text, paragraphs separated by blank lines. Unlike 'description' "
        "this is never sent to a model, so it can be as long as it needs to be",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(),
        description="When the bundle was created",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(onupdate=utcnow),
        description="When the bundle was last changed",
    )
