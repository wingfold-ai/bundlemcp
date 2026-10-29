from pydantic import BaseModel, ConfigDict, Field

KIB = 1024
MIB = 1024 * KIB


class RuntimeSettings(BaseModel):
    """Every runtime-tunable setting with its type, default and bounds.

    The registry of keys an operator may store is derived from these fields,
    so a setting is declared here and nowhere else. An instance holds the
    values in effect: the stored overrides, and the defaults for the rest.
    """

    model_config = ConfigDict(frozen=True)

    call_timeout: float = Field(
        default=60.0,
        description="Seconds a single upstream tool call may take before the gateway gives up",
    )
    reset_timeout_on_progress: bool = Field(
        default=True,
        description="Whether an upstream progress notification restarts the call timeout",
    )
    max_total_timeout: float = Field(
        default=1800.0,
        description="Absolute ceiling in seconds for one upstream tool call, progress or not",
    )
    session_lifetime: int = Field(
        default=86400,
        ge=0,
        description="Idle lifetime in seconds of a session record; 0 disables idle expiry",
    )
    list_cache_ttl_ms: int = Field(
        default=300000,
        description="Milliseconds a client may keep a tools, prompts or resources list",
    )
    server_error_attempts: int = Field(
        default=3,
        ge=1,
        description="Consecutive connection failures, across every replica, before an upstream "
        "is marked as in error",
    )
    audit_retention_days: int = Field(
        default=90,
        ge=0,
        description="Days an audit record is kept before it is purged; 0 keeps everything",
    )
    authorization_code_lifetime: int = Field(
        default=600,
        description="Seconds a client has to redeem an authorization code from the gateway",
    )
    access_token_lifetime: int = Field(
        default=3600, description="Seconds an access token from the gateway stays valid"
    )
    refresh_token_lifetime: int = Field(
        default=604800, description="Seconds a refresh token from the gateway stays valid"
    )
    max_request_bytes: int = Field(
        default=4 * MIB,
        ge=64 * KIB,
        le=64 * MIB,
        description="Largest request body the gateway accepts, in bytes",
    )
    max_upstream_response_bytes: int = Field(
        default=16 * MIB,
        ge=64 * KIB,
        le=64 * MIB,
        description="Largest single message the gateway reads from an upstream, in bytes",
    )
    upstream_sessions_max: int = Field(
        default=256, ge=1, description="Upstream sessions one replica holds open in all"
    )
    upstream_sessions_per_server_max: int = Field(
        default=32, ge=1, description="Upstream sessions one replica holds open per upstream"
    )
    upstream_session_idle_timeout: int = Field(
        default=300,
        ge=1,
        description="Seconds an unused pooled upstream session is kept before it is closed",
    )
