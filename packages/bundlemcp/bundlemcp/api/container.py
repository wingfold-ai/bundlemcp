"""Everything the running app holds, as one typed object."""

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bundlemcp.crypto import TokenCipher
from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.discovery import DiscoveryService
from bundlemcp.gateway.mcp_endpoint import McpEdge
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.ratelimit import AuthFailureGuard, AuthFailureLimiter, RateLimiter
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.oauth.oidc import OidcProvider
from bundlemcp.oauth.upstream_client import UpstreamTokenStore
from bundlemcp.services import UpstreamConnectionRegistry
from bundlemcp.settings import Settings
from bundlemcp.store import UnitOfWorkFactory
from bundlemcp.store.admin_sessions import AdminSessionStore
from bundlemcp.store.invalidation import InvalidationSubscriber


class AppContainer(BaseModel):
    """The composed object graph, published once on ``app.state.container``.

    Every field is required unless its absence is a real deployment state, so a
    half-wired app cannot be constructed. Providers read one field each; nothing
    downstream reaches for a bare ``app.state`` attribute.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    settings: Settings = Field(repr=False, description="Deploy-time configuration")
    engine: AsyncEngine = Field(description="Async engine over the durable store")
    session_factory: async_sessionmaker[AsyncSession] = Field(
        description="Opens database sessions for request and background work"
    )
    redis: Redis = Field(description="Client for the live store")
    unit_of_work_factory: UnitOfWorkFactory = Field(
        description="Opens a transaction that publishes its invalidation events on commit"
    )
    discovery: DiscoveryService = Field(description="Probes upstream servers for their tools")
    audit: AuditWriter = Field(description="Queued writer for audit records")
    runtime_config: RuntimeConfig = Field(description="Runtime-tunable config, cached per replica")
    counters: Counters = Field(description="In-process metric sink")
    rate_limiter: RateLimiter = Field(description="Fixed-window limits shared by every edge")
    auth_failure_limiter: AuthFailureLimiter = Field(
        description="Per-IP counter of failed authentications"
    )
    auth_failure_guard: AuthFailureGuard = Field(
        description="Per-IP lockout after repeated bad credentials, for every credential edge"
    )
    token_cipher: TokenCipher | None = Field(  # DEP-9
        repr=False,
        description="Encrypts stored upstream secrets; None until encryption keys are configured",
    )
    upstream_tokens: UpstreamTokenStore | None = Field(  # spec 23
        description="Store for upstream OAuth tokens; None when no encryption keys are configured"
    )
    upstream_connections: UpstreamConnectionRegistry = Field(
        description="Connection state of upstream OAuth as the management API reports it"
    )
    admin_sessions: AdminSessionStore = Field(description="Browser sessions for the admin UI")
    oidc_provider: OidcProvider | None = Field(
        description="The identity provider admins log in with; None when none is configured"
    )
    invalidation: InvalidationSubscriber = Field(
        description="This replica's subscription to configuration changes"
    )
    mcp_edge: McpEdge = Field(description="The Streamable-HTTP edge serving every endpoint")
