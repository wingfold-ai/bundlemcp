import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, Index
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class AuditRecord(SQLModel, table=True):
    """Append-only per-tool-call record; nullable FKs + denormalized names survive deletes."""

    __tablename__ = "audit_records"
    __table_args__ = (
        Index("ix_audit_created_endpoint", "created_at", "endpoint_name"),
        Index("ix_audit_status", "status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts(index=True))
    endpoint_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("endpoints.id", ondelete="SET NULL"), nullable=True),
    )
    endpoint_name: str
    bundle_name: str
    server_name: str | None = None
    tool_name: str | None = None  # original upstream name
    presented_tool_name: str | None = None  # after prefix/override/profile
    user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    api_key_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
    )
    auth_method: str | None = None  # oauth | api_key | none
    session_id: str | None = None
    status: str  # AuditStatus
    denied_reason: str | None = None  # AUD-2
    duration_ms: int | None = None
    error_message: str | None = None  # truncated (AUD-1)
