"""The deploy-time configuration model."""

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

from bundlemcp.domain.access.identity_subject import IdentitySubject
from bundlemcp.domain.oauth.redirect_uri_allow_list import RedirectUriAllowList


class Settings(BaseModel):
    """Deploy-time configuration, as every layer reads it; the loader that fills it from the
    environment lives in infrastructure."""

    # Stores
    database_url: str = Field(
        default="postgresql+asyncpg://bundlemcp:bundlemcp@localhost:5432/bundlemcp",
        description="Async SQLAlchemy connection string for the Postgres that holds "
        "configuration, tokens and the audit log",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Connection string for the Valkey holding live sessions, "
        "rate-limit counters and cross-replica signalling",
    )

    public_url: AnyHttpUrl = Field(
        default=AnyHttpUrl("http://localhost:8000"),
        description="Externally reachable base URL of this gateway. The OAuth issuer, "
        "discovery metadata, redirect URIs and cookie scope all derive from it, so it "
        "must match what clients actually reach — never the internal listen address",
    )
    trusted_proxies: list[str] = Field(
        default=[],
        description="CIDRs of reverse proxies whose X-Forwarded-* headers are honoured. "
        "Requests from anywhere else use the socket peer address, so a wrong value here "
        "makes per-client rate limits and audit records attribute to the proxy",
    )

    # Admin auth (the auth spec)
    oidc_discovery_url: str | None = Field(
        default=None,
        description="OIDC issuer's discovery document URL; admin login is disabled when unset. "
        "It and the endpoints it names are subject to the egress policy, so an issuer on "
        "loopback needs an egress allow entry",
    )
    oidc_client_id: str | None = Field(
        default=None, description="Client id registered with the OIDC provider"
    )
    oidc_client_secret: str | None = Field(
        default=None, description="Client secret registered with the OIDC provider"
    )
    admin_emails: list[str] = Field(
        default=[],
        description="Email addresses granted admin rights, re-evaluated at every login",
    )
    admin_claim: str = Field(
        default="groups",
        min_length=1,
        description="ID-token claim that grants admin rights when it equals or contains "
        "admin_claim_value; a dotted path reaches into nested claims, e.g. "
        "'realm_access.roles' for Keycloak realm roles. Re-evaluated at every login",
    )
    admin_claim_value: str = Field(
        default="bundlemcp-admin",
        min_length=1,
        description="Value of admin_claim that grants admin rights, e.g. a group or role name",
    )
    admin_session_lifetime: int = Field(
        default=43200,
        ge=300,
        le=2592000,
        description="Seconds an admin UI login lasts before the user must sign in again at the "
        "identity provider (12 hours by default); between 300 and 2592000 (30 days)",
    )

    web_origins: list[str] = Field(
        default=[],
        description="Browser origins allowed to call the management API with credentials. "
        "They also pass the CSRF origin check on cookie-authenticated mutations. "
        "Empty means same-origin only, which is what an API-only deployment wants",
    )

    egress_allow_cidrs: list[str] = Field(
        default=[],
        description="CIDRs outbound requests may resolve to; empty allows anything not denied. "
        "Checked first and overrides every other rule, including the built-in loopback and "
        "cloud-metadata blocks, so keep it as narrow as the host you mean to reach",
    )
    egress_deny_cidrs: list[str] = Field(
        default=[],
        description="CIDRs outbound requests may never resolve to, evaluated after the allow "
        "list, so an allow entry covering the same address wins",
    )

    config_cache_disabled: bool = Field(
        default=False,
        description="Read runtime configuration from the database on every access instead of "
        "caching it per replica. A debugging aid: behaviour is identical, only slower",
    )
    shutdown_drain_seconds: int = Field(
        default=20,
        ge=1,
        le=600,
        description="Seconds a stopping replica lets in-flight requests finish before it exits. "
        "It reports not ready and refuses new requests at once, ends its notification streams, "
        "and answers calls still running at the end with an error. Keep the orchestrator's stop "
        "grace period above it",
    )
    discovery_refresh_interval: int = Field(
        default=1800,
        ge=0,
        description="Seconds between re-reading every upstream server's tool list, so tools "
        "of a server that was unreachable when registered, or that changed without notice, "
        "show up without a manual refresh. One replica refreshes per interval. 0 disables it",
    )

    token_encryption_keys: list[str] = Field(
        default=[],
        description="Keys for encrypting stored upstream OAuth tokens. The first encrypts and "
        "all of them decrypt, so rotation means prepending a key and keeping the old one. "
        "Servers using upstream OAuth cannot be used while this is empty",
    )
    token_reencryption_interval: int = Field(
        default=3600,
        ge=0,
        description="Seconds between passes that re-encrypt stored upstream tokens and client "
        "secrets under the first of BUNDLEMCP_TOKEN_ENCRYPTION_KEYS, so an older key can be "
        "dropped once a pass logs remaining_on_old_key=0. One replica runs each pass. 0 "
        "disables the passes; values are still re-encrypted when they are read",
    )

    metering_hook: str | None = Field(
        default=None,
        description="Import path 'module:attribute' of the billing hook consulted around every "
        "tool call; unset installs a no-op hook",
    )
    metering_hook_fail_open: bool = Field(
        default=False,
        description="Whether a tool call proceeds when the metering hook itself fails. "
        "False denies the call, which is the safe default for a paid deployment",
    )
    metering_http_url: str | None = Field(
        default=None,
        pattern=r"^https?://",
        description="URL of a metering hook that runs out of process, consulted over HTTP "
        "around every tool call instead of an in-process hook, e.g. "
        "'http://metering:8000/hook'. The gateway POSTs a pre-call and a post-call event "
        "there; see the metering hook documentation for the bodies. Cannot be combined with "
        "an in-process metering hook",
    )
    metering_http_token: str | None = Field(
        default=None,
        description="Bearer token the gateway sends to the out-of-process metering hook. Keep "
        "it in a secret store; it is never logged",
    )
    metering_http_timeout: float = Field(
        default=2.0,
        gt=0,
        le=30,
        description="Seconds the out-of-process metering hook has to answer a pre-call before "
        "the call is treated as unanswered and, by default, denied",
    )

    identity_subject: IdentitySubject = Field(
        default=IdentitySubject.INTERNAL,
        description="Which identifier the X-MCP-User header names a signed-in user by: "
        "'internal' sends the gateway's own user id, stable only within this gateway's "
        "database; 'oidc' sends the identity provider's subject, stable across logins and "
        "database rebuilds. API-key callers are sent as 'api_key:<id>' either way. Changing "
        "it changes the key upstream servers see for every existing user",
    )

    # Auth-failure limiter: gateway-wide, per client IP.
    auth_failure_limit: int = Field(
        default=20,
        ge=1,
        description="Failed authentication attempts from one IP before it is locked out",
    )
    auth_failure_window: int = Field(
        default=300,
        ge=1,
        description="Seconds the auth-failure count is retained before the lockout lifts",
    )

    # Client registration with the gateway's OAuth server
    dcr_allowed_redirect_uris: list[str] = Field(
        default_factory=list,
        description="Redirect URIs OAuth clients may register or declare in a client metadata "
        "document. Each entry is an exact URI, compared character for character, or a URI "
        "whose leftmost host label is '*' (e.g. 'https://*.example.com/oauth/callback'), "
        "which matches exactly one DNS label in that position with the same scheme, port, "
        "path and query. Empty accepts any https URI, or http on localhost. Registrations "
        "whose redirect URIs are all listed are exempt from the per-IP registration limit",
    )
    dcr_rate_limit: int = Field(
        default=10,
        ge=1,
        le=100_000,
        description="Dynamic client registrations one client IP may make per window. Behind a "
        "shared egress, such as a hosted AI client registering from its own servers, every "
        "user of that client shares this budget",
    )
    dcr_rate_window: int = Field(
        default=3600,
        ge=1,
        le=86_400,
        description="Seconds in the per-IP registration window",
    )
    dcr_max_unused_clients: int = Field(
        default=1000,
        ge=1,
        le=1_000_000,
        description="Maximum number of registered OAuth clients that have not yet obtained a "
        "token, across all IPs. Once reached, further registrations are refused with HTTP 429 "
        "until clients are used or the periodic purge removes those unused for seven days. "
        "Applies to every registration, allow-listed or not",
    )

    # Bootstrap (the management spec)
    bootstrap_file: str | None = Field(
        default=None,
        description="Path to a declarative document (YAML or JSON) of servers, bundles and "
        "endpoints applied at startup; applying it twice changes nothing",
    )
    bootstrap: str | None = Field(
        default=None,
        description="The same document inline as JSON, for a compose file or a secret store "
        "that cannot mount a file. Applied after the file when both are set",
    )
    bootstrap_strict: bool = Field(
        default=False,
        description="Whether a failed bootstrap refuses startup. True belongs in CI and "
        "production; false logs and continues, which suits local development",
    )
    initial_service_key: str | None = Field(
        default=None,
        description="Value of a service API key provisioned on first boot when no service key "
        "exists yet, so the management API is reachable headlessly. Ignored once one exists",
    )

    legacy_protocol_enabled: bool = Field(
        default=True,
        description="Whether the session-era MCP revisions (2025-03-26 through 2025-11-25, "
        "which open with an initialize handshake and hold a session) are still served. Switch "
        "off once every client speaks the stateless 2026-07-28 revision, which is unaffected "
        "either way; a session-era client then fails at initialize",
    )

    log_level: str = Field(
        default="INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum severity written to the structured log",
    )
    log_format: str = Field(
        default="json",
        pattern=r"^(json|text)$",
        description="Log line format for every logger in the process, the web server's "
        "included: 'json' for a log pipeline, 'text' for a terminal",
    )

    @field_validator("dcr_allowed_redirect_uris")
    @classmethod
    def _parse_redirect_uri_patterns(cls, value: list[str]) -> list[str]:
        RedirectUriAllowList.of(value)  # refuses a malformed entry at startup, naming it
        return value

    @property
    def public_base(self) -> str:
        """The public URL as a bare origin-plus-path string, without a trailing slash."""
        return str(self.public_url).rstrip("/")

    @model_validator(mode="after")
    def _one_metering_hook(self) -> "Settings":
        # one hook per deployment, in-process or over HTTP
        if self.metering_hook and self.metering_http_url:
            raise ValueError(
                "set BUNDLEMCP_METERING_HOOK or BUNDLEMCP_METERING_HTTP_URL, not both"
            )
        return self
