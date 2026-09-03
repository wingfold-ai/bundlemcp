"""The deploy-time configuration model."""

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUNDLEMCP_", env_file=".env", extra="ignore")

    # Stores (ARC-7/ARC-8)
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

    public_url: AnyHttpUrl = Field(  # DEP-1
        default=AnyHttpUrl("http://localhost:8000"),
        description="Externally reachable base URL of this gateway. The OAuth issuer, "
        "discovery metadata, redirect URIs and cookie scope all derive from it, so it "
        "must match what clients actually reach — never the internal listen address",
    )
    trusted_proxies: list[str] = Field(  # DEP-2
        default=[],
        description="CIDRs of reverse proxies whose X-Forwarded-* headers are honoured. "
        "Requests from anywhere else use the socket peer address, so a wrong value here "
        "makes per-client rate limits and audit records attribute to the proxy",
    )

    # Admin auth (spec 21)
    oidc_discovery_url: str | None = Field(
        default=None,
        description="OIDC issuer's discovery document URL; admin login is disabled when unset",
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

    web_origins: list[str] = Field(  # SEC-4, UI-5
        default=[],
        description="Browser origins allowed to call the management API with credentials. "
        "They also pass the CSRF origin check on cookie-authenticated mutations. "
        "Empty means same-origin only, which is what an API-only deployment wants",
    )

    egress_allow_cidrs: list[str] = Field(  # SEC-2
        default=[],
        description="CIDRs upstream servers may resolve to; empty allows anything not denied",
    )
    egress_deny_cidrs: list[str] = Field(  # SEC-2
        default=[],
        description="CIDRs upstream servers may never resolve to, evaluated after the allow "
        "list. Cloud metadata ranges are blocked in code regardless of this setting",
    )

    token_encryption_keys: list[str] = Field(  # DEP-9
        default=[],
        description="Keys for encrypting stored upstream OAuth tokens. The first encrypts and "
        "all of them decrypt, so rotation means prepending a key and keeping the old one. "
        "Servers using upstream OAuth cannot be used while this is empty",
    )

    metering_hook: str | None = Field(  # MID-3
        default=None,
        description="Import path 'module:attribute' of the billing hook consulted around every "
        "tool call; unset installs a no-op hook",
    )
    metering_hook_fail_open: bool = Field(
        default=False,
        description="Whether a tool call proceeds when the metering hook itself fails. "
        "False denies the call, which is the safe default for a paid deployment",
    )

    # Auth-failure limiter (RATE-5): gateway-wide, per client IP.
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

    # Bootstrap (spec 41)
    bootstrap_file: str | None = Field(
        default=None,
        description="Path to a declarative document of servers, bundles and endpoints applied "
        "at startup; applying it twice changes nothing",
    )
    bootstrap_strict: bool = Field(
        default=False,
        description="Whether a failed bootstrap refuses startup. True belongs in CI and "
        "production; false logs and continues, which suits local development",
    )
    initial_service_key: str | None = Field(  # BOOT-3
        default=None,
        description="Value of a service API key provisioned on first boot when no service key "
        "exists yet, so the management API is reachable headlessly. Ignored once one exists",
    )

    log_level: str = Field(
        default="INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Minimum severity written to the structured log",
    )

    @property
    def public_base(self) -> str:
        """The public URL as a bare origin-plus-path string, without a trailing slash."""
        return str(self.public_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings, read from the environment once."""
    return Settings()
