"""Building the edge from the collaborators the composition root has acquired."""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.dialect import DialectRegistry
from bundlemcp.gateway.mcp_endpoint.authentication import EndpointAuthentication
from bundlemcp.gateway.mcp_endpoint.cache_hints import CacheHints
from bundlemcp.gateway.mcp_endpoint.handlers import (
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
from bundlemcp.gateway.mcp_endpoint.mcp_edge import McpEdge
from bundlemcp.gateway.mcp_endpoint.method_registry import MethodRegistry
from bundlemcp.gateway.mcp_endpoint.rate_limit_gate import RateLimitGate
from bundlemcp.gateway.mcp_endpoint.rate_limited import RateLimited
from bundlemcp.gateway.mcp_endpoint.tool_call import ToolCallSupport, ToolsCallHandler
from bundlemcp.gateway.mcp_endpoint.upstream_credentials import UpstreamCredentialResolver
from bundlemcp.gateway.metering import MeteringHook
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.ratelimit import AuthFailureGuard, RateLimiter
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.oauth.upstream_client import UpstreamTokenStore
from bundlemcp.settings import Settings
from bundlemcp.store.sessions import SessionStore


class McpEdgeAssembly(BaseModel):
    """The inputs to one MCP edge, and the recipe that wires them into handlers.

    Every field is required apart from ``upstream_tokens``, which is None exactly
    when no token encryption keys are configured.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    settings: Settings = Field(repr=False, description="Deploy-time configuration")
    session_factory: async_sessionmaker[AsyncSession] = Field(
        description="Opens the short database session that admits each request"
    )
    sessions: SessionStore = Field(description="Session records in Valkey")
    registry: StreamRegistry = Field(description="This replica's open streams and in-flight calls")
    signals: SignalBus = Field(description="Cross-replica delivery of cancels, replies and events")
    metering: MeteringHook = Field(description="Billing hook consulted around every tool call")
    audit: AuditWriter = Field(description="Queued writer for audit records")
    client_factory: ClientFactory = Field(description="Builds an MCP client for an upstream server")
    runtime_config: RuntimeConfig = Field(description="Runtime-tunable config, cached per replica")
    upstream_tokens: UpstreamTokenStore | None = Field(
        description="Store for upstream OAuth tokens; None when no encryption keys are configured"
    )
    rate_limiter: RateLimiter = Field(description="Fixed-window limits per endpoint and client")
    auth_failures: AuthFailureGuard = Field(description="Per-IP lockout on bad credentials")
    counters: Counters = Field(description="In-process metric sink")

    def build(self) -> McpEdge:
        dialects = DialectRegistry.default(legacy_enabled=self.settings.legacy_protocol_enabled)
        cache_hints = CacheHints(self.runtime_config)
        gate = RateLimitGate(self.rate_limiter, self.counters, self.settings)
        credentials = UpstreamCredentialResolver(self.upstream_tokens, self.settings.public_base)
        fanout = MemberFanout(self.client_factory, credentials)
        tool_calls = ToolsCallHandler(
            ToolCallSupport(
                metering=self.metering,
                audit=self.audit,
                credentials=credentials,
                client_factory=self.client_factory,
                sessions=self.sessions,
                registry=self.registry,
                signals=self.signals,
                runtime_config=self.runtime_config,
                metering_fail_open=self.settings.metering_hook_fail_open,
            )
        )
        methods = MethodRegistry(
            {
                "ping": PingHandler(),
                "server/discover": RateLimited(
                    ServerDiscoverHandler(dialects, cache_hints), gate, tool_call=False
                ),
                "tools/list": RateLimited(ToolsListHandler(cache_hints), gate, tool_call=False),
                "tools/call": RateLimited(tool_calls, gate, tool_call=True),
                "prompts/list": PromptsListHandler(fanout, cache_hints),
                "prompts/get": PromptsGetHandler(fanout),
                "completion/complete": CompletionHandler(fanout),
                "resources/list": ResourcesListHandler(fanout, cache_hints),
                "resources/templates/list": ResourceTemplatesListHandler(fanout, cache_hints),
                "resources/read": ResourcesReadHandler(fanout),
                "resources/subscribe": ResourcesSubscribeHandler(),
                "resources/unsubscribe": ResourcesSubscribeHandler(),
                "logging/setLevel": LoggingSetLevelHandler(self.sessions),
                "subscriptions/listen": SubscriptionsListenHandler(self.registry),
                "notifications/cancelled": CancelledNotificationHandler(self.signals),
            }
        )
        return McpEdge(
            session_factory=self.session_factory,
            sessions=self.sessions,
            registry=self.registry,
            signals=self.signals,
            authentication=EndpointAuthentication(),
            auth_failures=self.auth_failures,
            dialects=dialects,
            initialize=RateLimited(
                InitializeHandler(self.sessions, dialects), gate, tool_call=False
            ),
            methods=methods,
            public_base=self.settings.public_base,
        )
