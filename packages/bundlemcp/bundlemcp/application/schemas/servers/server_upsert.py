from typing import Literal

from pydantic import BaseModel, Field, field_validator

from bundlemcp.domain.servers.forward_header_rules import is_forwardable
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.shared.resource_names import ServerName


class ServerUpsert(BaseModel):
    """Body for POST /upstreams and PUT /upstreams/{name}."""

    name: ServerName = Field(
        description="Unique server name: letters, digits, underscores and hyphens, without a "
        "double underscore because that separates server from tool in presented tool names"
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
        description="Client headers to pass through, mapped from incoming name to upstream name. "
        "Host, cookie, content-length, x-api-key, mcp-session-id and any sec-* or proxy-* "
        "header are refused. Forwarding 'authorization' passes the caller's gateway token "
        "through; prefer auth_mode 'delegated_token'",
    )
    auth_mode: ServerAuthMode = Field(
        default=ServerAuthMode.NONE,
        description="How the gateway authenticates to this server: 'none' or 'static_headers' "
        "(which of the two is derived from whether static headers are stored), "
        "'upstream_oauth' (the gateway holds OAuth tokens from the server's authorization "
        "server) or 'delegated_token' (each call carries a short-lived token the gateway "
        "issues for the caller, valid only at this server, which the server verifies through "
        "the gateway's introspection endpoint). Run POST /upstreams:inspect to learn which one "
        "a server needs",
    )
    identity_mode: IdentityMode = Field(
        default=IdentityMode.SHARED,
        description="Whether all callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool | None = Field(  # SRV-13
        default=None,
        description="Whether the calling user's identity is sent to the server as X-MCP-User. "
        "Omitted on create, it is on for a server on the gateway's own network and off for "
        "any public host; omitted on update, the stored value is kept",
    )
    protocol_mode: str | None = Field(  # SRV-10
        default=None,
        pattern=r"^(auto|legacy|\d{4}-\d{2}-\d{2})$",
        description="How the gateway negotiates the MCP revision with this server: 'auto' "
        "(probe server/discover, fall back to the initialize handshake), 'legacy' (always "
        "the handshake, for servers whose tools need server-initiated requests), or a "
        "revision date such as '2026-07-28' to pin that revision. Omitted on create it is "
        "'auto'; omitted on update, the stored value is kept",
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

    @field_validator("forward_headers")
    @classmethod
    def forwardable(cls, v: dict[str, str]) -> dict[str, str]:
        # SRV-14 / FWD-2: refused at write time, not only skipped at call time
        refused = sorted(name for pair in v.items() for name in pair if not is_forwardable(name))
        if refused:
            raise ValueError(f"headers that are never forwarded: {', '.join(refused)}")
        return v

    @field_validator("url")
    @classmethod
    def url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v
