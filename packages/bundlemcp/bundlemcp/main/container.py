"""Everything the running app holds, as one typed object."""

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bundlemcp.api.http.auth_failure_guard import AuthFailureGuard
from bundlemcp.api.mcp.routing.gateway_router import McpGatewayRouter
from bundlemcp.api.oauth.browser_state.oidc_login_state import OidcLoginState
from bundlemcp.api.oauth.browser_state.upstream_connect_state import UpstreamConnectState
from bundlemcp.application.contracts.identity.oidc_provider import OidcProvider
from bundlemcp.application.contracts.live_state.admin_session_store import AdminSessionStore
from bundlemcp.application.contracts.live_state.auth_failure_limiter import AuthFailureLimiter
from bundlemcp.application.contracts.live_state.counters import Counters
from bundlemcp.application.contracts.live_state.rate_limiter import RateLimiter
from bundlemcp.application.contracts.live_state.single_use_state import SingleUseState
from bundlemcp.application.contracts.persistence.audit_sink import AuditSink
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.readiness_probe import ReadinessProbe
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.upstream_connection_registry import (
    UpstreamConnectionRegistry,
)
from bundlemcp.application.discovery.discovery_service import DiscoveryService
from bundlemcp.application.oauth_server import ClientMetadataFetcher, PendingAuthorization
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.application.settings.settings import Settings
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.infrastructure.valkey.invalidation_subscriber import InvalidationSubscriber


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
    audit: AuditSink = Field(description="Queued writer for audit records")
    runtime_config: RuntimeConfig = Field(description="Runtime-tunable config, cached per replica")
    counters: Counters = Field(description="In-process metric sink")
    rate_limiter: RateLimiter = Field(description="Fixed-window limits shared by every edge")
    auth_failure_limiter: AuthFailureLimiter = Field(
        description="Per-IP counter of failed authentications"
    )
    auth_failure_guard: AuthFailureGuard = Field(
        description="Per-IP lockout after repeated bad credentials, for every credential edge"
    )
    token_cipher: SecretCipher | None = Field(  # DEP-9
        repr=False,
        description="Encrypts stored upstream secrets; None until encryption keys are configured",
    )
    upstream_tokens: UpstreamTokenService | None = Field(  # spec 23
        description="Store for upstream OAuth tokens; None when no encryption keys are configured"
    )
    upstream_connections: UpstreamConnectionRegistry = Field(
        description="Connection state of upstream OAuth as the management API reports it"
    )
    admin_sessions: AdminSessionStore = Field(description="Browser sessions for the admin UI")
    readiness: ReadinessProbe = Field(description="Checks that every store answers")
    pending_authorizations: SingleUseState[PendingAuthorization] = Field(
        description="Authorization requests parked while the consent screen is shown"
    )
    oidc_login_states: SingleUseState[OidcLoginState] = Field(
        description="Login attempts parked while the identity provider authenticates"
    )
    connect_states: SingleUseState[UpstreamConnectState] = Field(
        description="Upstream connect flows parked while the upstream authorizes"
    )
    oidc_provider: OidcProvider | None = Field(
        description="The identity provider admins log in with; None when none is configured"
    )
    client_metadata: ClientMetadataFetcher = Field(
        description="Resolves URL-shaped OAuth client ids to their metadata documents"
    )
    invalidation: InvalidationSubscriber = Field(
        description="This replica's subscription to configuration changes"
    )
    mcp_router: McpGatewayRouter = Field(
        description="The Streamable-HTTP front controller serving every endpoint"
    )
