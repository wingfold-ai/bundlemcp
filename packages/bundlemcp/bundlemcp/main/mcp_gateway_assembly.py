"""Building the MCP gateway from the collaborators the composition root has acquired."""

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.mcp.dispatch.handlers import (
    CancelledNotificationHandler,
    CompletionHandler,
    InitializeHandler,
    LoggingSetLevelHandler,
    MemberFanout,
    PingHandler,
    PromptsGetHandler,
    PromptsListHandler,
    ResourcesListHandler,
    ResourcesReadHandler,
    ResourcesSubscribeHandler,
    ResourceTemplatesListHandler,
    ServerDiscoverHandler,
    SubscriptionsListenHandler,
    ToolsListHandler,
)
from bundlemcp.api.mcp.dispatch.handlers.input_required_bridge import InputRequiredBridge
from bundlemcp.api.mcp.dispatch.method_registry import MethodRegistry
from bundlemcp.api.mcp.dispatch.rate_limit_gate import RateLimitGate
from bundlemcp.api.mcp.dispatch.rate_limited import RateLimited
from bundlemcp.api.mcp.protocol.cache_hints import CacheHints
from bundlemcp.api.mcp.protocol.dialect import DialectRegistry
from bundlemcp.api.mcp.protocol.header_forwarding import HeaderForwarding
from bundlemcp.api.mcp.routing.adapters import SessionMcpAdapter, StatelessMcpAdapter
from bundlemcp.api.mcp.routing.admission_gate import AdmissionGate
from bundlemcp.api.mcp.routing.authentication import EndpointAuthentication
from bundlemcp.api.mcp.routing.gateway_router import McpGatewayRouter
from bundlemcp.api.mcp.routing.session_stream import SessionStream
from bundlemcp.api.mcp.tool_call import ToolCallSupport, ToolsCallHandler
from bundlemcp.application.contracts.live_state.paused_invocations import PausedInvocations
from bundlemcp.application.contracts.live_state.rate_limiter import RateLimiter
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_presence import StreamPresence
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.observability.call_tracer import CallTracer
from bundlemcp.application.contracts.observability.gateway_metrics import GatewayMetrics
from bundlemcp.application.contracts.persistence.audit_sink import AuditSink
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.delegation.delegated_token_issuer import DelegatedTokenIssuer
from bundlemcp.application.discovery.upstream_health import UpstreamHealth
from bundlemcp.application.metering.metering_hook import MeteringHook
from bundlemcp.application.metering.metering_stage import MeteringStage
from bundlemcp.application.serving.audit_stage import AuditStage
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.application.serving.replica_drain import ReplicaDrain
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.settings.settings import Settings
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.endpoints.profiles.profile_catalog import ProfileCatalog
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class McpGatewayAssembly(BaseModel):
    """The collaborators one MCP gateway is built from, and the recipe that wires them.

    Every field is required apart from ``upstream_tokens`` and ``state_cipher``,
    which are None exactly when no token encryption keys are configured.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    settings: Settings = Field(repr=False, description="Deploy-time configuration")
    unit_of_work_factory: UnitOfWorkFactory = Field(
        description="Opens the short transaction that admits each request"
    )
    sessions: SessionStore = Field(description="Session records in Valkey")
    registry: StreamRegistry = Field(description="This replica's open streams and in-flight calls")
    drain: ReplicaDrain = Field(description="Refuses new requests once this replica is draining")
    signals: SignalBus = Field(description="Cross-replica delivery of cancels, replies and events")
    presence: StreamPresence = Field(
        description="Which notification streams some replica holds, for failing fast without one"
    )
    metering: MeteringHook = Field(description="Billing hook consulted around every tool call")
    paused_invocations: PausedInvocations = Field(
        description="Metered invocations waiting for client input, shared by every replica"
    )
    audit: AuditSink = Field(description="Queued writer for audit records")
    client_factory: UpstreamClientFactory = Field(
        description="Builds an MCP client for an upstream server"
    )
    runtime_config: RuntimeConfig = Field(description="Runtime-tunable config, cached per replica")
    tracer: CallTracer = Field(description="Where the span of each upstream tool call goes")
    upstream_health: UpstreamHealth = Field(
        description="Counts live calls that could not reach their upstream toward its health"
    )
    upstream_tokens: UpstreamTokenService | None = Field(
        description="Store for upstream OAuth tokens; None when no encryption keys are configured"
    )
    delegated_tokens: DelegatedTokenIssuer = Field(
        description="Issues the upstream-bound tokens delegated_token servers receive"
    )
    state_cipher: SecretCipher | None = Field(
        description="Seals a modern client's requestState; None when no encryption keys are "
        "configured"
    )
    rate_limiter: RateLimiter = Field(description="Fixed-window limits per endpoint and client")
    auth_failures: AuthFailureGuard = Field(description="Per-IP lockout on bad credentials")
    metrics: GatewayMetrics = Field(description="Where calls, limits and listings are counted")
    profiles: ProfileCatalog = Field(
        description="The registered endpoint profiles a served tool list is shaped by"
    )
    clock: Clock = Field(description="Where the edge reads the time when it checks a credential")
    secret_hasher: SecretHasher = Field(description="How a presented credential is digested")

    def build(self) -> McpGatewayRouter:
        dialects = DialectRegistry.default(legacy_enabled=self.settings.legacy_protocol_enabled)
        cache_hints = CacheHints(self.runtime_config)
        gate = RateLimitGate(self.rate_limiter, self.metrics, self.settings)
        credentials = UpstreamCredentialResolver(
            self.upstream_tokens, self.settings.public_base, delegated=self.delegated_tokens
        )
        connect_prompts = AccountConnectPrompts(credentials)
        header_forwarding = HeaderForwarding(self.settings.identity_subject)
        fanout = MemberFanout(
            self.client_factory,
            credentials,
            header_forwarding,
            self.registry,
            self.signals,
            self.presence,
            self.runtime_config,
        )
        content = BundleContentReader(self.unit_of_work_factory)
        bridge = InputRequiredBridge(
            fanout, self.registry, self.signals, self.runtime_config, self.state_cipher
        )
        tool_calls = ToolsCallHandler(
            ToolCallSupport(
                call_stages=(
                    MeteringStage(
                        hook=self.metering,
                        invocations=self.paused_invocations,
                        fail_open=self.settings.metering_hook_fail_open,
                    ),
                    AuditStage(sink=self.audit),
                ),
                profiles=self.profiles,
                audit=self.audit,
                credentials=credentials,
                header_forwarding=header_forwarding,
                client_factory=self.client_factory,
                sessions=self.sessions,
                registry=self.registry,
                signals=self.signals,
                presence=self.presence,
                runtime_config=self.runtime_config,
                metrics=self.metrics,
                upstream_health=self.upstream_health,
                tracer=self.tracer,
                state_cipher=self.state_cipher,
            ),
            connect_prompts,
        )
        # each member is reached per request, so nothing listens for a member's
        # list changes or resource updates; they are not advertised either
        member_notifications = False
        methods = MethodRegistry(
            {
                "ping": PingHandler(),
                "server/discover": RateLimited(
                    ServerDiscoverHandler(
                        dialects, cache_hints, member_notifications=member_notifications
                    ),
                    gate,
                    tool_call=False,
                ),
                "tools/list": RateLimited(
                    ToolsListHandler(cache_hints, connect_prompts, self.metrics),
                    gate,
                    tool_call=False,
                ),
                "tools/call": RateLimited(tool_calls, gate, tool_call=True),
                "prompts/list": PromptsListHandler(fanout, cache_hints),
                "prompts/get": PromptsGetHandler(fanout, content, bridge),
                "completion/complete": CompletionHandler(fanout),
                "resources/list": ResourcesListHandler(fanout, cache_hints),
                "resources/templates/list": ResourceTemplatesListHandler(fanout, cache_hints),
                "resources/read": ResourcesReadHandler(fanout, content, cache_hints, bridge),
                "resources/subscribe": ResourcesSubscribeHandler(),
                "resources/unsubscribe": ResourcesSubscribeHandler(),
                "logging/setLevel": LoggingSetLevelHandler(self.sessions),
                "subscriptions/listen": SubscriptionsListenHandler(self.registry, self.presence),
                "notifications/cancelled": CancelledNotificationHandler(self.signals),
            }
        )
        stream = SessionStream(self.registry, self.sessions, self.runtime_config, self.presence)
        session_adapter = SessionMcpAdapter(
            sessions=self.sessions,
            runtime_config=self.runtime_config,
            signals=self.signals,
            dialects=dialects,
            initialize=RateLimited(
                InitializeHandler(
                    self.sessions,
                    dialects,
                    self.runtime_config,
                    member_notifications=member_notifications,
                ),
                gate,
                tool_call=False,
            ),
            methods=methods,
            stream=stream,
        )
        stateless_adapter = StatelessMcpAdapter(dialects=dialects, methods=methods)
        admission = AdmissionGate(
            unit_of_work_factory=self.unit_of_work_factory,
            authentication=EndpointAuthentication(clock=self.clock, hasher=self.secret_hasher),
            auth_failures=self.auth_failures,
            audit=self.audit,
            public_base=self.settings.public_base,
            profiles=self.profiles,
        )
        return McpGatewayRouter(
            drain=self.drain,
            admission=admission,
            stateless_adapter=stateless_adapter,
            session_adapter=session_adapter,
        )
