from pydantic import BaseModel, Field

from bundlemcp.application.schemas.servers.oauth_inspection import OAuthInspection
from bundlemcp.application.schemas.servers.server_info_read import ServerInfoRead
from bundlemcp.application.schemas.servers.server_upsert import ServerUpsert
from bundlemcp.domain.servers.connection_state import ConnectionState


class ServerInspection(BaseModel):
    """What an upstream is, as far as it can be learnt without registering it."""

    url: str = Field(description="The URL that was inspected")
    connection_state: ConnectionState = Field(
        description="ready (it answered as an MCP server), oauth_required, credential_required "
        "(refused without OAuth metadata: it wants an API key or token header), "
        "insufficient_scope, not_mcp, unreachable, egress_denied or error"
    )
    detail: str | None = Field(
        default=None,
        description="Why the probe got no MCP answer, when it did not; header values never "
        "appear here",
    )
    protocol_version: str | None = Field(
        default=None, description="MCP revision negotiated with the server, when it answered"
    )
    server_info: ServerInfoRead | None = Field(
        default=None, description="How the server describes itself, when it answered"
    )
    tool_names: list[str] = Field(
        default=[], description="Names of the tools the server lists, when it answered"
    )
    oauth: OAuthInspection | None = Field(
        default=None, description="The authorization chain, for an OAuth-protected server"
    )
    suggested_url: str | None = Field(
        default=None,
        description="A nearby URL that does answer as MCP (such as the same URL with /mcp "
        "appended), when the given one is not an MCP endpoint",
    )
    hints: list[str] = Field(
        default=[], description="Plain-language notes on what to do next, most important first"
    )
    suggestion: ServerUpsert = Field(
        description="A registration derived from what was found: submit it to PUT "
        "/upstreams/{name} as is, adding the credential headers the server needs"
    )
