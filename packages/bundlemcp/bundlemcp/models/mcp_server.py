import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow
from bundlemcp.models.health_status import HealthStatus
from bundlemcp.models.identity_mode import IdentityMode
from bundlemcp.models.server_auth_mode import ServerAuthMode


class McpServer(SQLModel, table=True):
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
    auth_mode: str = Field(
        default=ServerAuthMode.NONE,
        description="How the gateway authenticates to this server",
    )
    identity_mode: str = Field(
        default=IdentityMode.SHARED,
        description="Whether callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool = Field(  # FWD-3
        default=True,
        description="Whether the calling user's identity is forwarded upstream",
    )
    capabilities: dict = Field(  # DISC-6, source for PROT-11 aggregation
        default_factory=dict,
        sa_column=Column(JSON),
        description="What the server advertised at its last probe. A key is present exactly "
        "when that capability was advertised",
    )
    health_status: str = Field(
        default=HealthStatus.UNKNOWN,
        description="Result of the most recent probe: ok, error or unknown",
    )
    last_error: str | None = Field(default=None, description="Why the last probe failed, if it did")
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=_ts(), description="When the record was created"
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=_ts(onupdate=utcnow),
        description="When the record was last changed",
    )
