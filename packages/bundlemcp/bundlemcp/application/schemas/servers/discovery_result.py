from pydantic import BaseModel, Field

from bundlemcp.domain.servers.connection_state import ConnectionState


class DiscoveryResult(BaseModel):
    """Outcome of one probe against an upstream server."""

    discovered: int = Field(default=0, description="Tools the upstream reported in this probe")
    changed: int = Field(
        default=0,
        description="Tools whose cached state changed: new, redefined, no longer listed "
        "(now stale) or listed again",
    )
    pruned: int = Field(
        default=0,
        ge=0,
        description="Stale tools deleted, with their curation in every bundle; only a refresh "
        "that asks to prune deletes any",
    )
    error: str | None = Field(
        default=None,
        description="Why the probe failed; None when it succeeded",
    )
    connection_state: ConnectionState = Field(
        default=ConnectionState.UNKNOWN,
        description="What the probe found out about the upstream: ready on success, otherwise "
        "why it gave no MCP answer (oauth_required, credential_required, not_mcp, "
        "unreachable, ...)",
    )
