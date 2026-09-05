from typing import Literal

from pydantic import BaseModel, Field, field_validator

from bundlemcp.models import IdentityMode, ServerAuthMode
from bundlemcp.schemas.resource_names import ServerName


class ServerUpsert(BaseModel):
    """Body for POST /servers and PUT /servers/{name}."""

    name: ServerName = Field(
        description="Unique server name; lowercase letters, digits and hyphens, and it may "
        "not contain a double underscore because that separates server from tool"
    )
    description: str | None = Field(
        default=None, description="Free-text note about what this server provides"
    )
    url: str = Field(description="Streamable HTTP URL of the upstream MCP server")
    static_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers sent on every upstream request, for credentials the server needs. "
        "Values are write-only and never returned",
    )
    forward_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Client headers to pass through, mapped from incoming name to upstream name",
    )
    auth_mode: ServerAuthMode = Field(
        default=ServerAuthMode.NONE,
        description="How the gateway authenticates to this server",
    )
    identity_mode: IdentityMode = Field(
        default=IdentityMode.SHARED,
        description="Whether all callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool = Field(
        default=True,
        description="Whether the calling user's identity is forwarded to the upstream server",
    )
    protocol_mode: str = Field(  # SRV-10
        default="auto",
        pattern=r"^(auto|legacy|\d{4}-\d{2}-\d{2})$",
        description="How the gateway negotiates the MCP revision with this server: 'auto' "
        "(probe server/discover, fall back to the initialize handshake), 'legacy' (always "
        "the handshake, for servers whose tools need server-initiated requests), or a "
        "revision date such as '2026-07-28' to pin that revision",
    )
    transport: Literal["streamable-http"] | None = Field(  # API-4
        default=None,
        description="Upstream transport. Only streamable-http is supported; the field exists "
        "so payloads that state it explicitly are accepted",
    )
    force: bool = Field(  # SRV-5
        default=False,
        description="Confirm a rename that would otherwise be rejected, accepting that bundles "
        "and tool names derived from the old name change with it",
    )

    @field_validator("url")
    @classmethod
    def url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v
