import asyncio

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.api.mcp.protocol.header_forwarding import HeaderForwarding
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_presence import StreamPresence
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.observability.call_tracer import CallTracer
from bundlemcp.application.contracts.persistence.audit_sink import AuditSink
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.discovery.upstream_health import UpstreamHealth
from bundlemcp.application.serving.chain_stage import ChainStage
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog


class ToolCallSupport(BaseModel):
    """The collaborators every tools/call needs, held once by the handler."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    call_stages: tuple[ChainStage, ...] = Field(
        description="The chain's stages that act on calls, in order: metering, then audit"
    )
    profiles: ProfileCatalog = Field(
        description="The registered profiles, whose presentation stages open each call's chain"
    )
    audit: AuditSink = Field(
        description="Where the record of a call that never resolved to a tool goes"
    )
    credentials: UpstreamCredentialResolver = Field(
        description="Resolves the upstream Authorization header for the caller"
    )
    client_factory: UpstreamClientFactory = Field(
        description="Builds the MCP client for the upstream"
    )
    header_forwarding: HeaderForwarding = Field(
        description="Client headers passed through and the identity header the gateway adds"
    )
    sessions: SessionStore = Field(description="Records the upstream binding on the session")
    registry: StreamRegistry = Field(
        description="In-flight calls and reply futures on this replica"
    )
    signals: SignalBus = Field(description="Reaches the replica holding the client's stream")
    presence: StreamPresence = Field(
        description="Whether any replica holds the client's stream, before a request is sent on it"
    )
    runtime_config: RuntimeConfig = Field(description="Source of the call timeouts")
    tracer: CallTracer = Field(description="Where the span of each upstream call goes")
    upstream_health: UpstreamHealth = Field(
        description="Where a call reports whether it reached its upstream"
    )
    state_cipher: SecretCipher | None = Field(
        description="Seals the requestState a modern client echoes on a retry; None when no "
        "token encryption keys are configured, which makes input_required unavailable"
    )
    resume_grace: float = Field(
        default=2.0,
        gt=0,
        description="Seconds a retry waits for some replica to claim its answers before the "
        "parked call is presumed lost and the call is re-run",
    )
    detached: set[asyncio.Task] = Field(
        default_factory=set,
        description="Runners of streamed calls, kept alive past their response until done",
    )
