"""The ``mcp_servers`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, String, text
from sqlmodel import Field, SQLModel

from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class McpServerRow(SQLModel, table=True):
    __tablename__ = "mcp_servers"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the server"
    )
    name: str = Field(unique=True, index=True, description="Unique server name")
    description: str | None = Field(
        default=None, description="Free-text note about what this server provides"
    )
    url: str = Field(description="Streamable HTTP URL the server is reached at")
    static_headers: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Headers sent on every upstream request, for credentials the server needs",
    )
    forward_headers: dict[str, str] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Client headers passed through, mapped from incoming to upstream name",
    )
    auth_mode: ServerAuthMode = Field(
        default=ServerAuthMode.NONE,
        sa_type=String,
        description="How the gateway authenticates to this server",
    )
    identity_mode: IdentityMode = Field(
        default=IdentityMode.SHARED,
        sa_type=String,
        description="Whether callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool = Field(
        default=True,
        description="Whether the calling user's identity is forwarded upstream",
    )
    capabilities: dict = Field(  # source for capability aggregation
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
        description="What the server advertised at its last probe. A key is present exactly "
        "when that capability was advertised",
    )
    protocol_mode: str = Field(
        default="auto",
        sa_type=String,
        description="How the gateway negotiates the MCP revision with this server: 'auto' "
        "probes server/discover and falls back to the initialize handshake, 'legacy' always "
        "uses the handshake, and a revision date pins that revision",
    )
    protocol_version: str | None = Field(
        default=None,
        description="MCP revision negotiated at the last successful probe, absent until then",
    )
    health_status: HealthStatus = Field(
        default=HealthStatus.UNKNOWN,
        sa_type=String,
        description="Result of the most recent probe: ok, error or unknown",
    )
    last_error: str | None = Field(default=None, description="Why the last probe failed, if it did")
    connection_state: ConnectionState = Field(
        default=ConnectionState.UNKNOWN,
        sa_column=Column(String, nullable=False, server_default=text("'unknown'")),
        description="What the last probe found out about the upstream, classified from its "
        "HTTP response",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(),
        description="When the record was created",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(onupdate=utcnow),
        description="When the record was last changed",
    )
