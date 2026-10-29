from typing import Literal

from pydantic import BaseModel, Field, field_validator

from bundlemcp.domain.servers.forward_header_rules import is_forwardable
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.listing_snapshot_mode import ListingSnapshotMode
from bundlemcp.domain.servers.protocol_mode import NegotiationMode, ProtocolMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.servers.server_changes import ServerChanges
from bundlemcp.domain.shared.resource_names import ServerName

DEPRECATED_SESSION_ALIAS = "legacy"
"""Accepted in place of ``session`` on every write, and never returned."""


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
    send_identity_header: bool | None = Field(
        default=None,
        description="Whether the calling user's identity is sent to the server as X-MCP-User. "
        "Omitted on create, it is on for a server on the gateway's own network and off for "
        "any public host; omitted on update, the stored value is kept",
    )
    protocol_mode: ProtocolMode | None = Field(
        default=None,
        description="How the gateway negotiates the MCP revision with this server: 'auto' "
        "(probe server/discover, fall back to the initialize handshake), 'session' (always "
        "the handshake and its session, for servers whose tools need server-initiated "
        "requests), or a revision date such as '2026-07-28' to pin that revision. 'legacy' is "
        "accepted as a deprecated alias of 'session' and read back as 'session'. Omitted on "
        "create it is 'auto'; omitted on update, the stored value is kept",
    )
    listing_snapshot: ListingSnapshotMode | None = Field(
        default=None,
        description="How prompts/list, resources/list and resources/templates/list are answered "
        "for this server's prompts and resources: 'auto' serves the listing stored at its last "
        "discovery when the server marked it public, or gave no cache scope and is sent nothing "
        "that depends on the caller (no forwarded headers, no X-MCP-User, no per-user or "
        "delegated tokens); 'shared' serves the stored listing to every caller, for a server that "
        "lists the same for everyone but is sent the caller's identity or marks its results "
        "private by default; 'live' always asks the server. Omitted on create it is 'auto'; "
        "omitted on update, the stored value is kept. Changing it does not contact the server",
    )
    transport: Literal["streamable-http"] | None = Field(
        default=None,
        description="Upstream transport. Only streamable-http is supported; the field exists "
        "so payloads that state it explicitly are accepted",
    )
    force: bool = Field(
        default=False,
        description="Confirm a rename that would otherwise be rejected, accepting that bundles "
        "and tool names derived from the old name change with it",
    )

    @field_validator("protocol_mode", mode="before")
    @classmethod
    def _session_alias(cls, value: object) -> object:
        # the handshake-only mode's pre-rename spelling, still sent by older clients and documents
        return NegotiationMode.SESSION if value == DEPRECATED_SESSION_ALIAS else value

    @field_validator("transport", mode="before")
    @classmethod
    def _only_streamable_http(cls, value: object) -> object:
        # Pydantic's literal error lists the allowed value but not why; name both
        if value is not None and value != "streamable-http":
            raise ValueError(
                f"transport must be 'streamable-http', the only transport this gateway "
                f"supports; got {value!r}"
            )
        return value

    @field_validator("forward_headers")
    @classmethod
    def forwardable(cls, v: dict[str, str]) -> dict[str, str]:
        # refused at write time, not only skipped at call time
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

    def changes(self) -> ServerChanges:
        """The configuration this body writes, without the name and the request-only flags."""
        return ServerChanges(
            description=self.description,
            url=self.url,
            static_headers=self.static_headers,
            forward_headers=self.forward_headers,
            auth_mode=self.auth_mode,
            identity_mode=self.identity_mode,
            send_identity_header=self.send_identity_header,
            protocol_mode=self.protocol_mode,
            listing_snapshot=self.listing_snapshot,
        )
