import uuid
from datetime import datetime
from typing import Self

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode


class ServerRead(EntityRead):
    """An upstream server as stored, with header values withheld."""

    id: uuid.UUID = Field(description="Identifier of the server")
    name: str = Field(description="Unique server name")
    description: str | None = Field(description="Free-text note about what this server provides")
    url: str = Field(description="Streamable HTTP URL the server is reached at")
    static_header_names: list[str] = Field(  # UPS-3
        default=[],
        description="Names of the headers sent upstream. Values are write-only and never "
        "leave the API, so only the names appear here",
    )
    forward_headers: dict[str, str] = Field(
        description="Client headers passed through, mapped from incoming name to upstream name"
    )
    auth_mode: ServerAuthMode = Field(
        description="How the gateway authenticates to this server: none, static_headers, "
        "upstream_oauth or delegated_token"
    )
    identity_mode: IdentityMode = Field(
        description="Whether callers share one upstream identity or each gets their own"
    )
    send_identity_header: bool = Field(
        description="Whether the calling user's identity is forwarded upstream"
    )
    capabilities: dict = Field(  # UPS-22
        default={},
        description="What the server advertised at its last probe: which of tools, prompts, "
        "resources, completions and logging it supports, with its listChanged and subscribe flags",
    )
    protocol_mode: str = Field(  # UPS-10
        description="How the gateway negotiates the MCP revision with this server: 'auto' "
        "(probe server/discover, fall back to initialize), 'legacy' (always initialize), "
        "or a pinned revision date such as '2026-07-28'",
    )
    protocol_version: str | None = Field(  # UPS-10
        description="MCP revision negotiated at the last successful probe; null until the "
        "server has been reached once"
    )
    health_status: HealthStatus = Field(
        description="Result of the most recent probe: ok, error or unknown"
    )
    last_error: str | None = Field(description="Why the last probe failed, if it did")
    connection_state: ConnectionState = Field(  # UPS-12
        description="What the last probe found out: ready, oauth_required, account_required, "
        "insufficient_scope, credential_required, not_mcp, unreachable, egress_denied, error, "
        "or unknown before the first probe"
    )
    configuration_mismatch: str | None = Field(  # UPS-12
        default=None,
        description="When the connection state contradicts the configuration, the change "
        "that would fix it; null otherwise",
    )
    forwards_caller_token: bool = Field(  # AUTH-33
        default=False,
        description="Whether a forward mapping passes the caller's own authorization header "
        "through to the server (token passthrough)",
    )
    created_at: datetime = Field(description="When the server was registered")
    updated_at: datetime = Field(description="When the server was last changed")

    @classmethod
    def from_entity(cls, entity: object) -> Self:
        server = entity if isinstance(entity, McpServer) else None
        if server is None:
            raise TypeError("ServerRead is built from an McpServer")
        data = {name: getattr(server, name) for name in McpServer.model_fields}
        data["static_header_names"] = sorted(server.static_headers)  # UPS-3: names only
        data["configuration_mismatch"] = server.configuration_mismatch
        data["forwards_caller_token"] = server.forwards_caller_token
        return cls.model_validate(data)
