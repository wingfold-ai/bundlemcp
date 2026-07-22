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

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None
    url: str
    static_headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    forward_headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    auth_mode: str = Field(default=ServerAuthMode.NONE)
    identity_mode: str = Field(default=IdentityMode.SHARED)
    send_identity_header: bool = Field(default=True)  # FWD-3
    # DISC-6: advertised-capability snapshot from the upstream initialize result
    # (source for PROT-11 aggregation). A key present == that capability advertised.
    capabilities: dict = Field(default_factory=dict, sa_column=Column(JSON))
    health_status: str = Field(default=HealthStatus.UNKNOWN)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))
