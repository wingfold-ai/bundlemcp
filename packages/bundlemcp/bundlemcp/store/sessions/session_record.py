from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.store.sessions._common import SESSION_RECORD_VERSION
from bundlemcp.store.sessions.upstream_binding import UpstreamBinding


class SessionRecord(BaseModel):
    """An MCP session as data in Valkey, so any replica can serve any request."""

    version: int = Field(
        default=SESSION_RECORD_VERSION,
        description="Schema version of this record, so a rollout can recognise older ones",
    )
    session_id: str = Field(description="Session identifier issued to the client")
    endpoint_name: str = Field(description="Endpoint the session was opened against")
    bundle_name: str = Field(description="Bundle that endpoint exposes")
    auth_method: str = Field(description="How the client authenticated: oauth, api_key or none")
    user_id: str | None = Field(default=None, description="Authenticated user, when OAuth was used")
    user_email: str | None = Field(
        default=None,
        description="Email of the authenticated user, passed on to the metering hook",
    )
    api_key_id: str | None = Field(default=None, description="API key used, when one was")
    protocol_version: str = Field(
        description="MCP protocol version negotiated when the session opened"
    )
    client_capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="What the client advertised it supports, which decides the relay handlers "
        "attached to upstream calls",
    )
    bindings: dict[str, UpstreamBinding] = Field(
        default_factory=dict,
        description="Attachments to upstream sessions, keyed by server name",
    )
