"""The domain layer: entities, value objects, enums and the rules they carry.

Entities are plain Pydantic models, one per module, grouped by context; how they
are stored is the persistence adapters' concern. Nothing here performs I/O.
"""

from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.user import User
from bundlemcp.domain.audit.audit_record import AuditRecord
from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.bundle_server import BundleServer
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.config.config_entry import ConfigEntry
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken
from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_consent import OAuthConsent
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.domain.upstream_oauth.upstream_oauth_token import UpstreamOAuthToken

__all__ = [
    "ApiKey",
    "AuditRecord",
    "Bundle",
    "BundleServer",
    "BundleTool",
    "ConfigEntry",
    "Endpoint",
    "McpServer",
    "OAuthAccessToken",
    "OAuthAuthorizationCode",
    "OAuthClient",
    "OAuthConsent",
    "Tool",
    "UpstreamOAuthClient",
    "UpstreamOAuthToken",
    "User",
]
