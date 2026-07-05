"""Domain entities — SQLModel classes serving as both DB tables AND Pydantic models.

Name rules are enforced on the API DTO layer (api/schemas/) and by
Postgres CHECK constraints added in the initial Alembic migration; table
models here stay validation-free because SQLModel skips validators for
table=True classes.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"
# Server names additionally must not contain "__" (DOM-4, BND-2).
RESERVED_ENDPOINT_NAMES = {
    "api",
    "oauth",
    ".well-known",
    "healthz",
    "readyz",
    "metrics",
    "docs",
    "login",
    "consent",
    "static",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ts(**kwargs: Any) -> Any:
    """Timezone-aware timestamp column."""
    return Column(DateTime(timezone=True), **kwargs)


class ServerAuthMode(StrEnum):
    NONE = "none"
    STATIC_HEADERS = "static_headers"
    UPSTREAM_OAUTH = "upstream_oauth"


class IdentityMode(StrEnum):
    SHARED = "shared"
    PER_USER = "per_user"


class HealthStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNKNOWN = "unknown"


class EndpointProfile(StrEnum):
    DEFAULT = "default"
    CLAUDE = "claude"
    CHATGPT = "chatgpt"


class EndpointAuthMode(StrEnum):
    OAUTH = "oauth"
    API_KEY = "api_key"
    NONE = "none"


class ApiKeyKind(StrEnum):
    ENDPOINT = "endpoint"
    SERVICE = "service"


class AuditStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"


class McpServer(SQLModel, table=True):
    __tablename__ = "mcp_servers"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None
    url: str
    static_headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    forward_headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    auth_mode: str = Field(default=ServerAuthMode.NONE)
    identity_mode: str = Field(default=IdentityMode.SHARED)
    send_identity_header: bool = Field(default=True)  # FWD-3
    # DISC-6: advertised-capability snapshot from the upstream initialize result
    # (source for PROT-11 aggregation). A key present == that capability advertised.
    capabilities: dict = Field(default_factory=dict, sa_column=Column(JSON))
    health_status: str = Field(default=HealthStatus.UNKNOWN)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))


class Tool(SQLModel, table=True):
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_tools_server_name"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True)
    )
    name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    annotations: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    schema_hash: str  # DISC-2
    last_seen_at: datetime = Field(default_factory=utcnow, sa_column=_ts())  # DISC-3


class Bundle(SQLModel, table=True):
    __tablename__ = "bundles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None  # served as MCP instructions (BND-1)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))


class BundleServer(SQLModel, table=True):
    __tablename__ = "bundle_servers"
    __table_args__ = (
        UniqueConstraint("bundle_id", "server_id", name="uq_bundle_servers_pair"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True)
    )
    enabled: bool = Field(default=True)  # BND-4


class BundleTool(SQLModel, table=True):
    __tablename__ = "bundle_tools"
    __table_args__ = (UniqueConstraint("bundle_id", "tool_id", name="uq_bundle_tools_pair"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    )
    tool_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    )
    enabled: bool = Field(default=True)  # TM-1
    override_name: str | None = None  # TM-3
    override_title: str | None = None
    override_description: str | None = None
    override_annotations: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Endpoint(SQLModel, table=True):
    __tablename__ = "endpoints"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)  # public URL segment (EP-1)
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    )
    profile: str = Field(default=EndpointProfile.DEFAULT)
    auth_modes: list[str] = Field(default_factory=lambda: ["api_key"], sa_column=Column(JSON))
    rate_limit: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_sub", name="uq_users_issuer_sub"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # the stable `sub`
    oidc_issuer: str
    oidc_sub: str
    email: str | None = Field(default=None, index=True)
    display_name: str | None = None
    is_admin: bool = Field(default=False)  # re-evaluated every login (ADM-3)
    is_active: bool = Field(default=True)  # ADM-6 deactivation
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class OAuthClient(SQLModel, table=True):
    __tablename__ = "oauth_clients"

    client_id: str = Field(primary_key=True)
    client_secret_hash: str | None = None  # None => public client (PKCE)
    client_name: str | None = None
    redirect_uris: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        sa_column=Column(JSON),
    )
    token_endpoint_auth_method: str = Field(default="none")
    scope: str = Field(default="mcp")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    last_used_at: datetime | None = Field(default=None, sa_column=_ts())  # SEC-8 purge


class OAuthAuthorizationCode(SQLModel, table=True):
    __tablename__ = "oauth_authorization_codes"

    code_hash: str = Field(primary_key=True)  # OAS-8: hashed at rest
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE"))
    )
    user_id: uuid.UUID = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE")))
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    )  # audience (OAS-10)
    redirect_uri: str
    scope: str = Field(default="mcp")
    code_challenge: str
    code_challenge_method: str = Field(default="S256")
    expires_at: datetime = Field(sa_column=_ts())
    used: bool = Field(default=False)  # single-use (OAS-3)


class OAuthAccessToken(SQLModel, table=True):
    __tablename__ = "oauth_access_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    access_token_hash: str = Field(unique=True, index=True)
    refresh_token_hash: str | None = Field(default=None, unique=True, index=True)
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE"))
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    )
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    )  # audience (OAS-10)
    scope: str = Field(default="mcp")
    expires_at: datetime = Field(sa_column=_ts())
    refresh_expires_at: datetime | None = Field(default=None, sa_column=_ts())
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class OAuthConsent(SQLModel, table=True):
    __tablename__ = "oauth_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", "endpoint_id", name="uq_consents_triple"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    )
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE"))
    )
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    )
    granted_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    revoked_at: datetime | None = Field(default=None, sa_column=_ts())


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    key_hash: str = Field(unique=True, index=True)  # KEY-1
    key_prefix: str  # display only
    kind: str = Field(default=ApiKeyKind.ENDPOINT)  # KEY-2
    endpoint_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # empty = all
    is_active: bool = Field(default=True)
    last_used_at: datetime | None = Field(default=None, sa_column=_ts())
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class UpstreamOAuthClient(SQLModel, table=True):
    __tablename__ = "upstream_oauth_clients"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), unique=True)
    )
    client_id: str | None = None
    client_secret_encrypted: str | None = None  # DOM-3 / DEP-9
    metadata_: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column("metadata", JSON)
    )  # discovered endpoints etc. (UPO-1)


class UpstreamOAuthToken(SQLModel, table=True):
    __tablename__ = "upstream_oauth_tokens"
    __table_args__ = (
        UniqueConstraint("server_id", "user_id", name="uq_upstream_tokens_server_user"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True)
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )  # NULL = shared/service connection (UPO-2)
    tokens_encrypted: str  # DOM-3
    expires_at: datetime | None = Field(default=None, sa_column=_ts())
    is_valid: bool = Field(default=True)  # UPO-4
    account_hint: str | None = None  # UPO-5 (e.g. masked account name)


class AuditRecord(SQLModel, table=True):
    """Append-only per-tool-call record; nullable FKs + denormalized names survive deletes."""

    __tablename__ = "audit_records"
    __table_args__ = (
        Index("ix_audit_created_endpoint", "created_at", "endpoint_name"),
        Index("ix_audit_status", "status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts(index=True))
    endpoint_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("endpoints.id", ondelete="SET NULL"), nullable=True),
    )
    endpoint_name: str
    bundle_name: str
    server_name: str | None = None
    tool_name: str | None = None  # original upstream name
    presented_tool_name: str | None = None  # after prefix/override/profile
    user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    api_key_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
    )
    auth_method: str | None = None  # oauth | api_key | none
    session_id: str | None = None
    status: str  # AuditStatus
    denied_reason: str | None = None  # AUD-2
    duration_ms: int | None = None
    error_message: str | None = None  # truncated (AUD-1)


class ConfigEntry(SQLModel, table=True):
    """Runtime-tunable key/value settings."""

    __tablename__ = "config_entries"

    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))
