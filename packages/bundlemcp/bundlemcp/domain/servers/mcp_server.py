import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.forward_header_rules import CALLER_TOKEN_HEADER
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode
from bundlemcp.domain.shared.clock import utcnow


class McpServer(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the server")
    name: str = Field(description="Unique server name")
    description: str | None = Field(
        default=None, description="Free-text note about what this server provides"
    )
    url: str = Field(description="Streamable HTTP URL the server is reached at")
    static_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers sent on every upstream request, for credentials the server needs",
    )
    forward_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Client headers passed through, mapped from incoming to upstream name",
    )
    auth_mode: ServerAuthMode = Field(
        default=ServerAuthMode.NONE,
        description="How the gateway authenticates to this server",
    )
    identity_mode: IdentityMode = Field(
        default=IdentityMode.SHARED,
        description="Whether callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool = Field(  # FWD-3
        default=True,
        description="Whether the calling user's identity is forwarded upstream",
    )
    capabilities: dict = Field(  # DISC-6, source for PROT-11 aggregation
        default_factory=dict,
        description="What the server advertised at its last probe. A key is present exactly "
        "when that capability was advertised",
    )
    protocol_mode: str = Field(  # SRV-10
        default="auto",
        description="How the gateway negotiates the MCP revision with this server: 'auto' "
        "probes server/discover and falls back to the initialize handshake, 'legacy' always "
        "uses the handshake, and a revision date pins that revision",
    )
    protocol_version: str | None = Field(  # SRV-10
        default=None,
        description="MCP revision negotiated at the last successful probe, absent until then",
    )
    health_status: HealthStatus = Field(
        default=HealthStatus.UNKNOWN,
        description="Result of the most recent probe: ok, error or unknown",
    )
    last_error: str | None = Field(default=None, description="Why the last probe failed, if it did")
    connection_state: ConnectionState = Field(  # SRV-12
        default=ConnectionState.UNKNOWN,
        description="What the last probe found out about the upstream, classified from its "
        "HTTP response",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the record was created",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        description="When the record was last changed",
    )

    @property
    def uses_upstream_oauth(self) -> bool:
        return self.auth_mode == ServerAuthMode.UPSTREAM_OAUTH

    @property
    def is_per_user(self) -> bool:
        return self.identity_mode == IdentityMode.PER_USER

    @property
    def uses_delegated_token(self) -> bool:
        return self.auth_mode == ServerAuthMode.DELEGATED_TOKEN

    # FWD-7
    @property
    def forwards_caller_token(self) -> bool:
        """The caller's own bearer is passed through to the upstream unchanged."""
        return any(header.lower() == CALLER_TOKEN_HEADER for header in self.forward_headers)

    @property
    def configuration_mismatch(self) -> str | None:
        """Why the last probe's finding contradicts how the server is configured, if it does.

        A server challenged for OAuth but not set up for it, or refused for a
        missing credential while holding none, will keep failing until the
        configuration changes, so this names the change.
        """
        state = self.connection_state
        if state == ConnectionState.OAUTH_REQUIRED and not self.uses_upstream_oauth:
            return "the server asks for OAuth sign-in; switch it to upstream OAuth"
        if (
            state == ConnectionState.CREDENTIAL_REQUIRED
            and not self.static_headers
            and not self.forward_headers
            and self.auth_mode != ServerAuthMode.DELEGATED_TOKEN
        ):
            return "the server refuses requests without a credential; add one as a header"
        return None

    @property
    def requires_per_user_token(self) -> bool:
        """Each caller must have connected their own upstream account to use this server."""
        return self.uses_upstream_oauth and self.is_per_user
