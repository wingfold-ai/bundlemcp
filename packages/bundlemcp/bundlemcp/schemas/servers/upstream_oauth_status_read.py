from pydantic import BaseModel, Field

from bundlemcp.models import IdentityMode
from bundlemcp.schemas.servers.upstream_connection_status import UpstreamConnectionStatus


class UpstreamOAuthStatusRead(BaseModel):
    """Connection state of a server's upstream OAuth, never its token values."""

    identity_mode: IdentityMode = Field(
        description="Whether callers share one upstream identity or each connects their own"
    )
    configured: bool = Field(
        description="Whether this gateway can store upstream tokens at all; false until token "
        "encryption keys are configured"
    )
    shared: UpstreamConnectionStatus | None = Field(
        default=None,
        description="State of the shared connection; null when upstream OAuth is not configured",
    )
    client_id: str | None = Field(
        default=None,
        description="Client id registered at the upstream authorization server; null until set",
    )
    authorization_url: str | None = Field(
        default=None,
        description="Operator-configured authorization endpoint; null when it is discovered",
    )
    token_url: str | None = Field(
        default=None,
        description="Operator-configured token endpoint; null when it is discovered",
    )
