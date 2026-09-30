from pydantic import BaseModel, Field

from bundlemcp.domain.servers.connection_state import ConnectionState


class DiscoveryResult(BaseModel):
    """Outcome of one probe against an upstream server."""

    discovered: int = Field(default=0, description="Tools the upstream reported in this probe")
    changed: int = Field(
        default=0,
        description="Tools written to the cache because their definition hash moved",
    )
    error: str | None = Field(
        default=None,
        description="Why the probe failed; None when it succeeded",
    )
    connection_state: ConnectionState = Field(  # SRV-12
        default=ConnectionState.UNKNOWN,
        description="What the probe found out about the upstream: ready on success, otherwise "
        "why it gave no MCP answer (oauth_required, credential_required, not_mcp, "
        "unreachable, ...)",
    )
