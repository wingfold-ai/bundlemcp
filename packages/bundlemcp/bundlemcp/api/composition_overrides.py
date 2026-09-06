"""The seams a test or an embedding application may substitute at composition time."""

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from bundlemcp.gateway.metering import MeteringHook
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.ratelimit import AuthFailureLimiter, RateLimiter
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.oauth.oidc import OidcProvider
from bundlemcp.oauth.upstream_client import UpstreamOAuthProvider
from bundlemcp.services.oauth_server import ClientMetadataFetcher


class CompositionOverrides(BaseModel):
    """Collaborators to use instead of the ones the composition root would build.

    Every field is genuinely optional: an unset seam means the real
    implementation. An injected engine or client stays owned by whoever passed
    it in and is not closed on shutdown.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    engine: AsyncEngine | None = Field(default=None, description="Database engine to reuse")
    redis: Redis | None = Field(default=None, description="Live-store client to reuse")
    client_factory: ClientFactory | None = Field(
        default=None, description="Builds the MCP client for an upstream server"
    )
    oidc_provider: OidcProvider | None = Field(
        default=None, description="Identity provider for admin login"
    )
    upstream_oidc_provider: UpstreamOAuthProvider | None = Field(
        default=None, description="Authorization-server client for upstream OAuth"
    )
    client_metadata_fetcher: ClientMetadataFetcher | None = Field(
        default=None, description="Resolver for URL-shaped OAuth client ids"
    )
    metering_hook: MeteringHook | None = Field(
        default=None, description="Billing hook consulted around every tool call"
    )
    counters: Counters | None = Field(default=None, description="Metric sink to record into")
    rate_limiter: RateLimiter | None = Field(
        default=None, description="Fixed-window limiter for endpoint and per-client limits"
    )
    auth_failure_limiter: AuthFailureLimiter | None = Field(
        default=None, description="Per-IP lockout after repeated authentication failures"
    )
