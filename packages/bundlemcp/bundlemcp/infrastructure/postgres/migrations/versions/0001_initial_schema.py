"""Initial schema, as it was at the first release.

Every table is spelled out so this revision produces the same schema in every
release; later revisions are explicit diffs on top of it. The timestamp
columns are plain timezone-aware DATETIMEs here — the entity models wrap them
in a TypeDecorator that only changes Python-side handling, not the DDL.

Postgres additionally enforces the name rules as CHECK constraints; hermetic
SQLite tests enforce them at the DTO layer instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME_RE = "^[a-zA-Z0-9_-]+$"


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("endpoint_ids", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=True)
    op.create_table(
        "bundles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bundles_name"), "bundles", ["name"], unique=True)
    op.create_table(
        "config_entries",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("static_headers", sa.JSON(), nullable=True),
        sa.Column("forward_headers", sa.JSON(), nullable=True),
        sa.Column("auth_mode", sa.String(), nullable=False),
        sa.Column("identity_mode", sa.String(), nullable=False),
        sa.Column("send_identity_header", sa.Boolean(), nullable=False),
        sa.Column("health_status", sa.String(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mcp_servers_name"), "mcp_servers", ["name"], unique=True)
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("client_secret_hash", sa.String(), nullable=True),
        sa.Column("client_name", sa.String(), nullable=True),
        sa.Column("redirect_uris", sa.JSON(), nullable=True),
        sa.Column("grant_types", sa.JSON(), nullable=True),
        sa.Column("token_endpoint_auth_method", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("client_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("oidc_issuer", sa.String(), nullable=False),
        sa.Column("oidc_sub", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("oidc_issuer", "oidc_sub", name="uq_users_issuer_sub"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_table(
        "bundle_servers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=True),
        sa.Column("server_id", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "server_id", name="uq_bundle_servers_pair"),
    )
    op.create_index(
        op.f("ix_bundle_servers_bundle_id"), "bundle_servers", ["bundle_id"], unique=False
    )
    op.create_index(
        op.f("ix_bundle_servers_server_id"), "bundle_servers", ["server_id"], unique=False
    )
    op.create_table(
        "endpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=True),
        sa.Column("profile", sa.String(), nullable=False),
        sa.Column("auth_modes", sa.JSON(), nullable=True),
        sa.Column("rate_limit", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_endpoints_bundle_id"), "endpoints", ["bundle_id"], unique=False)
    op.create_index(op.f("ix_endpoints_name"), "endpoints", ["name"], unique=True)
    op.create_table(
        "tools",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("input_schema", sa.JSON(), nullable=True),
        sa.Column("annotations", sa.JSON(), nullable=True),
        sa.Column("schema_hash", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "name", name="uq_tools_server_name"),
    )
    op.create_index(op.f("ix_tools_server_id"), "tools", ["server_id"], unique=False)
    op.create_table(
        "upstream_oauth_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=True),
        sa.Column("client_id", sa.String(), nullable=True),
        sa.Column("client_secret_encrypted", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id"),
    )
    op.create_table(
        "upstream_oauth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("server_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("tokens_encrypted", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("account_hint", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "user_id", name="uq_upstream_tokens_server_user"),
    )
    op.create_index(
        op.f("ix_upstream_oauth_tokens_server_id"),
        "upstream_oauth_tokens",
        ["server_id"],
        unique=False,
    )
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint_name", sa.String(), nullable=False),
        sa.Column("bundle_name", sa.String(), nullable=False),
        sa.Column("server_name", sa.String(), nullable=True),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("presented_tool_name", sa.String(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        sa.Column("auth_method", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("denied_reason", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_created_endpoint", "audit_records", ["created_at", "endpoint_name"], unique=False
    )
    op.create_index(
        op.f("ix_audit_records_created_at"), "audit_records", ["created_at"], unique=False
    )
    op.create_index("ix_audit_status", "audit_records", ["status"], unique=False)
    op.create_table(
        "bundle_tools",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=True),
        sa.Column("tool_id", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("override_name", sa.String(), nullable=True),
        sa.Column("override_title", sa.String(), nullable=True),
        sa.Column("override_description", sa.String(), nullable=True),
        sa.Column("override_annotations", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "tool_id", name="uq_bundle_tools_pair"),
    )
    op.create_index(op.f("ix_bundle_tools_bundle_id"), "bundle_tools", ["bundle_id"], unique=False)
    op.create_index(op.f("ix_bundle_tools_tool_id"), "bundle_tools", ["tool_id"], unique=False)
    op.create_table(
        "oauth_access_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("access_token_hash", sa.String(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(), nullable=True),
        sa.Column("client_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["oauth_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_oauth_access_tokens_access_token_hash"),
        "oauth_access_tokens",
        ["access_token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_oauth_access_tokens_refresh_token_hash"),
        "oauth_access_tokens",
        ["refresh_token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_oauth_access_tokens_user_id"), "oauth_access_tokens", ["user_id"], unique=False
    )
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("code_challenge", sa.String(), nullable=False),
        sa.Column("code_challenge_method", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["oauth_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_hash"),
    )
    op.create_table(
        "oauth_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("client_id", sa.String(), nullable=True),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["oauth_clients.client_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_id", "endpoint_id", name="uq_consents_triple"),
    )
    op.create_index(op.f("ix_oauth_consents_user_id"), "oauth_consents", ["user_id"], unique=False)

    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_mcp_servers_name",
            "mcp_servers",
            sa.text(f"name ~ '{_NAME_RE}' AND name NOT LIKE '%\\_\\_%'"),
        )
        op.create_check_constraint("ck_bundles_name", "bundles", sa.text(f"name ~ '{_NAME_RE}'"))
        op.create_check_constraint(
            "ck_endpoints_name", "endpoints", sa.text(f"name ~ '{_NAME_RE}'")
        )


def downgrade() -> None:
    op.drop_table("oauth_consents")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_access_tokens")
    op.drop_table("bundle_tools")
    op.drop_table("audit_records")
    op.drop_table("upstream_oauth_tokens")
    op.drop_table("upstream_oauth_clients")
    op.drop_table("tools")
    op.drop_table("endpoints")
    op.drop_table("bundle_servers")
    op.drop_table("users")
    op.drop_table("oauth_clients")
    op.drop_table("mcp_servers")
    op.drop_table("config_entries")
    op.drop_table("bundles")
    op.drop_table("api_keys")
