import uuid
from datetime import datetime
from typing import Self

from pydantic import Field

from bundlemcp.models import HealthStatus, IdentityMode, McpServer, ServerAuthMode
from bundlemcp.schemas.common.entity_read import EntityRead


class ServerRead(EntityRead):
    """An upstream server as stored, with header values withheld."""

    id: uuid.UUID = Field(description="Identifier of the server")
    name: str = Field(description="Unique server name")
    description: str | None = Field(description="Free-text note about what this server provides")
    url: str = Field(description="Streamable HTTP URL the server is reached at")
    static_header_names: list[str] = Field(  # SRV-3
        default=[],
        description="Names of the headers sent upstream. Values are write-only and never "
        "leave the API, so only the names appear here",
    )
    forward_headers: dict[str, str] = Field(
        description="Client headers passed through, mapped from incoming name to upstream name"
    )
    auth_mode: ServerAuthMode = Field(description="How the gateway authenticates to this server")
    identity_mode: IdentityMode = Field(
        description="Whether callers share one upstream identity or each gets their own"
    )
    send_identity_header: bool = Field(
        description="Whether the calling user's identity is forwarded upstream"
    )
    capabilities: dict = Field(  # DISC-6
        default={},
        description="What the server advertised at its last probe: which of tools, prompts, "
        "resources, completions and logging it supports, with its listChanged and subscribe flags",
    )
    health_status: HealthStatus = Field(
        description="Result of the most recent probe: ok, error or unknown"
    )
    last_error: str | None = Field(description="Why the last probe failed, if it did")
    created_at: datetime = Field(description="When the server was registered")
    updated_at: datetime = Field(description="When the server was last changed")

    @classmethod
    def from_entity(cls, entity: object) -> Self:
        server = entity if isinstance(entity, McpServer) else None
        if server is None:
            raise TypeError("ServerRead is built from an McpServer")
        data = {name: getattr(server, name) for name in McpServer.model_fields}
        data["static_header_names"] = sorted(server.static_headers)  # SRV-3: names only
        return cls.model_validate(data)
