from pydantic import BaseModel, ConfigDict, Field, field_validator

from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.metering import MeteringHook
from bundlemcp.gateway.metrics import Counters
from bundlemcp.gateway.ratelimit import RateLimiter
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.oauth.upstream_client import UpstreamTokenStore
from bundlemcp.settings import Settings
from bundlemcp.store.sessions import SessionStore


class GatewayRuntime(BaseModel):
    """Per-app gateway wiring (attached to app.state.gateway).

    Every field is required: the composition root always supplies all of them,
    so a half-wired runtime is unconstructable rather than an AttributeError
    somewhere down a request. `upstream_tokens` is the one genuine optional —
    it is None when no token encryption keys are configured — and must still
    be passed explicitly.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    sessions: SessionStore = Field(description="Session records in Valkey, readable by any replica")
    metering: MeteringHook = Field(description="Billing hook consulted before and after each call")
    audit: AuditWriter = Field(description="Queued writer for audit records, off the response path")
    client_factory: ClientFactory = Field(description="Builds an MCP client for an upstream server")
    runtime_config: RuntimeConfig = Field(description="Runtime-tunable config, cached per replica")
    registry: StreamRegistry = Field(  # SES-13
        description="Replica-pinned open streams, in-flight calls and reply futures",
    )
    signals: SignalBus = Field(  # SES-13
        description="Routes messages across replicas to whichever holds the target",
    )
    upstream_tokens: UpstreamTokenStore | None = Field(  # spec 23
        description="Store for upstream OAuth tokens; None when no encryption keys are configured",
    )
    public_url: str = Field(
        description="Externally reachable base URL, without a trailing slash",
    )
    rate_limiter: RateLimiter = Field(
        description="Fixed-window limits per endpoint and per client",
    )
    counters: Counters = Field(
        description="In-process metric sink the /metrics endpoint exports",
    )
    # repr=False: Settings holds the OIDC client secret, the initial service key
    # and the token encryption keys, and a nested model renders its fields. Keep
    # them out of any log line or traceback that reprs the runtime (DOM-3).
    settings: Settings = Field(
        repr=False,
        description="Deploy-time configuration, for trusted proxies and failure policy",
    )

    @field_validator("public_url", mode="before")
    @classmethod
    def _normalize_public_url(cls, value: object) -> str:
        """Settings carries an AnyHttpUrl; the gateway wants a bare, unslashed str."""
        return str(value).rstrip("/")
