from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.application.schemas.servers.server_info_read import ServerInfoRead


class InspectorConnection(BaseModel):
    """What a target reported when the inspector connected and initialised."""

    server_info: ServerInfoRead | None = Field(
        default=None, description="How the target describes itself, when it said"
    )
    protocol_version: str | None = Field(
        default=None, description="The MCP revision negotiated with the target"
    )
    capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="The capabilities the target advertised; a key is present exactly when "
        "that capability was advertised",
    )
    instructions: str | None = Field(
        default=None, description="The usage instructions the target sent, when it sent any"
    )
    initialize_ms: int = Field(
        ge=0, description="Milliseconds the connection and its initialisation took"
    )
