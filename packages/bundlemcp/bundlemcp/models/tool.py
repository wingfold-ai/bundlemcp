import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class Tool(SQLModel, table=True):
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_tools_server_name"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True)
    )
    name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    annotations: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    schema_hash: str  # DISC-2
    last_seen_at: datetime = Field(default_factory=utcnow, sa_column=_ts())  # DISC-3
