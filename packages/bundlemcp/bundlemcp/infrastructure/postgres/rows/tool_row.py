"""The ``tools`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class ToolRow(SQLModel, table=True):
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_tools_server_name"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the cached tool"
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True),
        description="Server that provides the tool",
    )
    name: str = Field(description="Tool name as the upstream server reports it")
    title: str | None = Field(default=None, description="Display title the upstream server reports")
    description: str | None = Field(
        default=None, description="Description the upstream server reports"
    )
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="JSON Schema for the tool's arguments",
    )
    annotations: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="MCP tool annotations such as read-only and destructive hints",
    )
    schema_hash: str = Field(
        description="Hash of the definition, so an unchanged tool costs no write on re-probe"
    )
    stale_since: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(nullable=True),
        description="When a successful discovery of the server first stopped listing the tool; "
        "None while the server lists it. A stale tool is not served but keeps its curation, "
        "and is served again if the server lists it again",
    )
