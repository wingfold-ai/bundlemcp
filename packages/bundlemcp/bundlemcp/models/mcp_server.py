import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, String
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
    health_status: HealthStatus = Field(
        default=HealthStatus.UNKNOWN,
        sa_type=String,
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

    @property
    def uses_upstream_oauth(self) -> bool:
        return self.auth_mode == ServerAuthMode.UPSTREAM_OAUTH

    @property
    def is_per_user(self) -> bool:
        return self.identity_mode == IdentityMode.PER_USER

    @property
    def requires_per_user_token(self) -> bool:
        """Each caller must have connected their own upstream account to use this server."""
        return self.uses_upstream_oauth and self.is_per_user
