from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.listing_snapshot_mode import ListingSnapshotMode
from bundlemcp.domain.servers.protocol_mode import ProtocolMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode


class ServerChanges(BaseModel):
    """One write of a server's configuration, as an operator or a document states it.

    Every field is applied as given, except where it says otherwise: the optional settings
    keep their stored value when ``None``, and an empty ``static_headers`` keeps the stored
    headers, because their values are never read back and so cannot be resent.
    """

    model_config = ConfigDict(frozen=True)

    description: str | None = Field(
        default=None, description="Free-text note about the server; None clears it"
    )
    url: str = Field(description="Streamable HTTP URL the server is reached at")
    static_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers sent on every upstream request; empty keeps the stored ones",
    )
    forward_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Client headers passed through, mapped from incoming to upstream name",
    )
    auth_mode: ServerAuthMode = Field(
        default=ServerAuthMode.NONE,
        description="How the gateway authenticates to the server; 'none' and 'static_headers' "
        "are settled by whether headers end up stored",
    )
    identity_mode: IdentityMode = Field(
        default=IdentityMode.SHARED,
        description="Whether callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool | None = Field(
        default=None,
        description="Whether the caller's identity is forwarded; None keeps the stored value, "
        "or on registration defaults by whether the host is on the gateway's own network",
    )
    protocol_mode: ProtocolMode | None = Field(
        default=None,
        description="How the MCP revision is negotiated; None keeps the stored value",
    )
    listing_snapshot: ListingSnapshotMode | None = Field(
        default=None,
        description="Whether listings are served from the discovery snapshot; None keeps the "
        "stored value",
    )
