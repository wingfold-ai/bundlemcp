from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.protocol_mode import ProtocolMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode


class DiscoveryInputs(BaseModel):
    """The part of a server's configuration that decides what a probe of it finds.

    Two servers with equal inputs reach the same upstream the same way, so a
    write that leaves them unchanged gives no reason to probe again.
    """

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="Streamable HTTP URL the upstream is reached at")
    static_headers: dict[str, str] = Field(description="Headers sent on every upstream request")
    forward_headers: dict[str, str] = Field(
        description="Client headers passed through, mapped from incoming to upstream name"
    )
    auth_mode: ServerAuthMode = Field(description="How the gateway authenticates upstream")
    identity_mode: IdentityMode = Field(
        description="Whether callers share one upstream identity or each gets their own"
    )
    send_identity_header: bool = Field(
        description="Whether the calling user's identity is forwarded upstream"
    )
    protocol_mode: ProtocolMode = Field(
        description="How the MCP revision is negotiated with the upstream: 'auto', 'session' "
        "or a pinned revision date"
    )
