"""The ``bundle_prompts`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class BundlePromptRow(SQLModel, table=True):
    __tablename__ = "bundle_prompts"
    __table_args__ = (UniqueConstraint("bundle_id", "name", name="uq_bundle_prompts_name"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the prompt"
    )
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True, nullable=False),
        description="Bundle the prompt belongs to",
    )
    name: str = Field(description="Prompt name, unique in its bundle")  # BPR-2
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(default=None, description="What the prompt is for")
    arguments: list[dict[str, Any]] = Field(  # BPR-1
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="Arguments the prompt takes, in display order",
    )
    messages: list[dict[str, Any]] = Field(  # BPR-1
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="Messages of the prompt, in conversation order",
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=timestamp_column(), description="When it was created"
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(onupdate=utcnow),
        description="When it last changed",
    )
