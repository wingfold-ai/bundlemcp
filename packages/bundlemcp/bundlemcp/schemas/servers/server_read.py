import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ServerRead(BaseModel):
    """An upstream server as stored, with header values withheld."""

    model_config = ConfigDict(from_attributes=True)

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
    auth_mode: str = Field(description="How the gateway authenticates to this server")
    identity_mode: str = Field(
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
    health_status: str = Field(description="Result of the most recent probe: ok, error or unknown")
    last_error: str | None = Field(description="Why the last probe failed, if it did")
    created_at: datetime = Field(description="When the server was registered")
    updated_at: datetime = Field(description="When the server was last changed")
