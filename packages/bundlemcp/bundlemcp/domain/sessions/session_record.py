from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding

SESSION_RECORD_VERSION = 2  # DEP-6: bump only with cross-release read compat


class SessionRecord(BaseModel):
    """An MCP session as data in Valkey, so any replica can serve any request."""

    version: int = Field(
        default=SESSION_RECORD_VERSION,
        description="Schema version of this record, so a rollout can recognise older ones",
    )
    session_id: str = Field(description="Session identifier issued to the client")
    endpoint_name: str = Field(description="Endpoint the session was opened against")
    bundle_name: str = Field(description="Bundle that endpoint exposes")
    identity: CallerIdentity = Field(
        description="Who opened the session, resolved once at initialize and reused for "
        "every call: metering, audit and header forwarding all read this"
    )
    protocol_version: str = Field(
        description="MCP protocol version negotiated when the session opened"
    )
    client_capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="What the client advertised it supports, which decides the relay handlers "
        "attached to upstream calls",
    )
    log_level: str | None = Field(  # PROT-7
        default=None,
        description="Minimum level of upstream log messages the client asked for with "
        "logging/setLevel; None until it asks",
    )
    bindings: dict[str, UpstreamBinding] = Field(
        default_factory=dict,
        description="Attachments to upstream sessions, keyed by server name",
    )

    def is_owned_by(self, caller: CallerIdentity) -> bool:
        """Whether ``caller`` opened this session: the same user, else the same API key.

        A session id is a bearer reference, so a caller that obtains another's id must not be
        able to use or end that session.
        """
        return self.identity.sub == caller.sub
