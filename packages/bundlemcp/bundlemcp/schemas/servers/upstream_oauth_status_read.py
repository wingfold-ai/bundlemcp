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
