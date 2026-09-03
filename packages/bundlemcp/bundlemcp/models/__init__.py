"""Domain entities: SQLModel classes serving as both DB tables AND Pydantic
models. One class per module; everything is re-exported here so consumers keep
importing from ``bundlemcp.models``, and importing this package registers every
table on ``SQLModel.metadata`` (which Alembic autogeneration relies on).
"""

from bundlemcp.models.api_key import ApiKey
from bundlemcp.models.api_key_kind import ApiKeyKind
from bundlemcp.models.audit_record import AuditRecord
from bundlemcp.models.audit_status import AuditStatus
from bundlemcp.models.base import NAME_PATTERN, RESERVED_ENDPOINT_NAMES, utcnow
from bundlemcp.models.bundle import Bundle
from bundlemcp.models.bundle_server import BundleServer
from bundlemcp.models.bundle_tool import BundleTool
from bundlemcp.models.caller_identity import API_KEY_SUBJECT_PREFIX, CallerIdentity
from bundlemcp.models.config_entry import ConfigEntry
from bundlemcp.models.endpoint import Endpoint
from bundlemcp.models.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.models.endpoint_profile import EndpointProfile
from bundlemcp.models.health_status import HealthStatus
from bundlemcp.models.identity_mode import IdentityMode
from bundlemcp.models.mcp_server import McpServer
from bundlemcp.models.oauth_access_token import OAuthAccessToken
from bundlemcp.models.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.models.oauth_client import OAuthClient
from bundlemcp.models.oauth_consent import OAuthConsent
from bundlemcp.models.presented_name import PRESENTED_NAME_SEPARATOR, PresentedName
from bundlemcp.models.server_auth_mode import ServerAuthMode
from bundlemcp.models.tool import Tool
from bundlemcp.models.upstream_oauth_client import UpstreamOAuthClient
from bundlemcp.models.upstream_oauth_token import UpstreamOAuthToken
from bundlemcp.models.user import User
from bundlemcp.models.utc_datetime import UtcDateTime

__all__ = [
    "API_KEY_SUBJECT_PREFIX",
    "NAME_PATTERN",
    "PRESENTED_NAME_SEPARATOR",
    "RESERVED_ENDPOINT_NAMES",
    "ApiKey",
    "ApiKeyKind",
    "AuditRecord",
    "AuditStatus",
    "Bundle",
    "BundleServer",
    "BundleTool",
    "CallerIdentity",
    "ConfigEntry",
    "Endpoint",
    "EndpointAuthMode",
    "EndpointProfile",
    "HealthStatus",
    "IdentityMode",
    "McpServer",
    "OAuthAccessToken",
    "OAuthAuthorizationCode",
    "OAuthClient",
    "OAuthConsent",
    "PresentedName",
    "ServerAuthMode",
    "Tool",
    "UpstreamOAuthClient",
    "UpstreamOAuthToken",
    "User",
    "UtcDateTime",
    "utcnow",
]
