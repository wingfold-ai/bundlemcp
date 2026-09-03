"""Framework-free business logic, one service class per resource.

Services take a unit of work plus the collaborators they need, return DTOs, and
raise the domain errors in ``bundlemcp.services.errors``; consumers (the
management API, the MCP edge, the OAuth endpoints, bootstrap) stay thin and map
failures at their own edge.
"""

from bundlemcp.services.api_key_service import ApiKeyService
from bundlemcp.services.audit_service import AuditFilter, AuditService
from bundlemcp.services.auth_service import (
    AdminSessionService,
    AuthService,
    Principal,
    PrincipalKind,
)
from bundlemcp.services.bundle_service import BundleService
from bundlemcp.services.config_service import ConfigService
from bundlemcp.services.endpoint_service import EndpointService
from bundlemcp.services.named_resource_service import NamedResourceService
from bundlemcp.services.no_upstream_connections import NoUpstreamConnections
from bundlemcp.services.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.services.per_user_upstream_policy import PerUserUpstreamPolicy
from bundlemcp.services.server_service import ServerService
from bundlemcp.services.tool_discovery import ToolDiscovery
from bundlemcp.services.upstream_connection_registry import UpstreamConnectionRegistry
from bundlemcp.services.upstream_oauth_config_service import UpstreamOAuthConfigService
from bundlemcp.services.user_service import UserService

__all__ = [
    "AdminSessionService",
    "ApiKeyService",
    "AuditFilter",
    "AuditService",
    "AuthService",
    "BundleService",
    "ConfigService",
    "EndpointService",
    "NamedResourceService",
    "NoUpstreamConnections",
    "NoopToolDiscovery",
    "PerUserUpstreamPolicy",
    "Principal",
    "PrincipalKind",
    "ServerService",
    "ToolDiscovery",
    "UpstreamConnectionRegistry",
    "UpstreamOAuthConfigService",
    "UserService",
]
