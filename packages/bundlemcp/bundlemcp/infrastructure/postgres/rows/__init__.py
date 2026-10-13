"""Row classes: one SQLModel table per entity. Importing this package registers every table on
``SQLModel.metadata``, which Alembic and ``create_all`` rely on. Mapping to and from the domain
entities is the repositories' job."""

from bundlemcp.infrastructure.postgres.rows.api_key_row import ApiKeyRow
from bundlemcp.infrastructure.postgres.rows.audit_record_row import AuditRecordRow
from bundlemcp.infrastructure.postgres.rows.bundle_prompt_row import BundlePromptRow
from bundlemcp.infrastructure.postgres.rows.bundle_resource_row import BundleResourceRow
from bundlemcp.infrastructure.postgres.rows.bundle_row import BundleRow
from bundlemcp.infrastructure.postgres.rows.bundle_server_row import BundleServerRow
from bundlemcp.infrastructure.postgres.rows.bundle_tool_row import BundleToolRow
from bundlemcp.infrastructure.postgres.rows.config_entry_row import ConfigEntryRow
from bundlemcp.infrastructure.postgres.rows.endpoint_row import EndpointRow
from bundlemcp.infrastructure.postgres.rows.mcp_server_row import McpServerRow
from bundlemcp.infrastructure.postgres.rows.oauth_access_token_row import OAuthAccessTokenRow
from bundlemcp.infrastructure.postgres.rows.oauth_authorization_code_row import (
    OAuthAuthorizationCodeRow,
)
from bundlemcp.infrastructure.postgres.rows.oauth_client_row import OAuthClientRow
from bundlemcp.infrastructure.postgres.rows.oauth_consent_row import OAuthConsentRow
from bundlemcp.infrastructure.postgres.rows.tool_row import ToolRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_client_row import UpstreamOAuthClientRow
from bundlemcp.infrastructure.postgres.rows.upstream_oauth_token_row import UpstreamOAuthTokenRow
from bundlemcp.infrastructure.postgres.rows.user_row import UserRow

__all__ = [
    "ApiKeyRow",
    "AuditRecordRow",
    "BundlePromptRow",
    "BundleResourceRow",
    "BundleRow",
    "BundleServerRow",
    "BundleToolRow",
    "ConfigEntryRow",
    "EndpointRow",
    "McpServerRow",
    "OAuthAccessTokenRow",
    "OAuthAuthorizationCodeRow",
    "OAuthClientRow",
    "OAuthConsentRow",
    "ToolRow",
    "UpstreamOAuthClientRow",
    "UpstreamOAuthTokenRow",
    "UserRow",
]
