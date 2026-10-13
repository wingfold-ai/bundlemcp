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
from bundlemcp.application.contracts.live_state.counters import Counters
from bundlemcp.application.contracts.live_state.rate_limiter import RateLimiter
from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.contracts.live_state.signal_bus import SignalBus
from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.persistence.audit_sink import AuditSink
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.upstream_client_factory import UpstreamClientFactory
from bundlemcp.application.delegation.delegated_token_issuer import DelegatedTokenIssuer
from bundlemcp.application.metering.metering_hook import MeteringHook
from bundlemcp.application.serving.bundle_content_reader import BundleContentReader
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.settings.settings import Settings
from bundlemcp.application.upstream_oauth.account_connect_prompts import AccountConnectPrompts
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
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
    signals: SignalBus = Field(description="Cross-replica delivery of cancels, replies and events")
    metering: MeteringHook = Field(description="Billing hook consulted around every tool call")
    audit: AuditSink = Field(description="Queued writer for audit records")
    client_factory: UpstreamClientFactory = Field(
        description="Builds an MCP client for an upstream server"
    )
    runtime_config: RuntimeConfig = Field(description="Runtime-tunable config, cached per replica")
    upstream_tokens: UpstreamTokenService | None = Field(
        description="Store for upstream OAuth tokens; None when no encryption keys are configured"
    )
    delegated_tokens: DelegatedTokenIssuer = Field(  # FWD-6
        description="Issues the upstream-bound tokens delegated_token servers receive"
    )
    state_cipher: SecretCipher | None = Field(
        description="Seals a modern client's requestState; None when no encryption keys are "
        "configured"
    )
    rate_limiter: RateLimiter = Field(description="Fixed-window limits per endpoint and client")
    auth_failures: AuthFailureGuard = Field(description="Per-IP lockout on bad credentials")
    counters: Counters = Field(description="In-process metric sink")
    clock: Clock = Field(description="Where the edge reads the time when it checks a credential")
    secret_hasher: SecretHasher = Field(description="How a presented credential is digested")

    def build(self) -> McpGatewayRouter:
        dialects = DialectRegistry.default(legacy_enabled=self.settings.legacy_protocol_enabled)
        cache_hints = CacheHints(self.runtime_config)
        gate = RateLimitGate(self.rate_limiter, self.counters, self.settings)
        credentials = UpstreamCredentialResolver(
            self.upstream_tokens, self.settings.public_base, delegated=self.delegated_tokens
        )
        connect_prompts = AccountConnectPrompts(credentials)  # UPO-3
        header_forwarding = HeaderForwarding(self.settings.identity_subject)  # FWD-3
        fanout = MemberFanout(
            self.client_factory,
            credentials,
            header_forwarding,
            self.registry,
            self.signals,
            self.runtime_config,
        )
        content = BundleContentReader(self.unit_of_work_factory)  # BPR-8
        tool_calls = ToolsCallHandler(
            ToolCallSupport(
                metering=self.metering,
                audit=self.audit,
                credentials=credentials,
                header_forwarding=header_forwarding,
                client_factory=self.client_factory,
                sessions=self.sessions,
                registry=self.registry,
                signals=self.signals,
                runtime_config=self.runtime_config,
                metering_fail_open=self.settings.metering_hook_fail_open,
                state_cipher=self.state_cipher,
            ),
            connect_prompts,
        )
        methods = MethodRegistry(
            {
                "ping": PingHandler(),
                "server/discover": RateLimited(
                    ServerDiscoverHandler(dialects, cache_hints), gate, tool_call=False
                ),
                "tools/list": RateLimited(
                    ToolsListHandler(cache_hints, connect_prompts), gate, tool_call=False
                ),
                "tools/call": RateLimited(tool_calls, gate, tool_call=True),
                "prompts/list": PromptsListHandler(fanout, cache_hints),
                "prompts/get": PromptsGetHandler(fanout, content),
                "completion/complete": CompletionHandler(fanout),
                "resources/list": ResourcesListHandler(fanout, cache_hints),
                "resources/templates/list": ResourceTemplatesListHandler(fanout, cache_hints),
                "resources/read": ResourcesReadHandler(fanout, content, cache_hints),
                "resources/subscribe": ResourcesSubscribeHandler(),
                "resources/unsubscribe": ResourcesSubscribeHandler(),
                "logging/setLevel": LoggingSetLevelHandler(self.sessions),
                "subscriptions/listen": SubscriptionsListenHandler(self.registry),
                "notifications/cancelled": CancelledNotificationHandler(self.signals),
            }
        )
        stream = SessionStream(self.registry, self.sessions)
        session_adapter = SessionMcpAdapter(
            sessions=self.sessions,
            signals=self.signals,
            dialects=dialects,
            initialize=RateLimited(
                InitializeHandler(self.sessions, dialects), gate, tool_call=False
            ),
            methods=methods,
            stream=stream,
        )
        stateless_adapter = StatelessMcpAdapter(dialects=dialects, methods=methods)
        admission = AdmissionGate(
            unit_of_work_factory=self.unit_of_work_factory,
            authentication=EndpointAuthentication(clock=self.clock, hasher=self.secret_hasher),
            auth_failures=self.auth_failures,
            public_base=self.settings.public_base,
        )
        return McpGatewayRouter(
            admission=admission,
            stateless_adapter=stateless_adapter,
            session_adapter=session_adapter,
        )
