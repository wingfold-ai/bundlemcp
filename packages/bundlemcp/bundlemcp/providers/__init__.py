"""FastAPI providers for the collaborators no single package owns.

These are app-owned dependency *providers*: each ``get_*`` reads a process-wide
collaborator that the composition root published on the app's container, or
builds a request-scoped service from one, and the ``*Provider`` alias injects it
into a route signature.

They live at the library level because the management-API controllers and the
OAuth controllers both consume them; a package that owns its own collaborators
exposes them from its own ``providers`` module instead.
"""

from bundlemcp.providers.collaborators import (
    RedisProvider,
    SessionFactoryProvider,
    SettingsProvider,
    UnitOfWorkProvider,
    get_app_settings,
    get_redis,
    get_session_factory,
    get_unit_of_work,
)
from bundlemcp.providers.services import (
    AdminSessionServiceProvider,
    ApiKeyServiceProvider,
    AuditServiceProvider,
    AuthServiceProvider,
    BundleServiceProvider,
    CallerResolverProvider,
    ConfigServiceProvider,
    EndpointServiceProvider,
    ServerServiceProvider,
    UpstreamOAuthConfigServiceProvider,
    UserServiceProvider,
    get_admin_session_service,
    get_api_key_service,
    get_audit_service,
    get_auth_service,
    get_bundle_service,
    get_config_service,
    get_endpoint_service,
    get_server_service,
    get_upstream_oauth_config_service,
    get_user_service,
)

__all__ = [
    "AdminSessionServiceProvider",
    "CallerResolverProvider",
    "ApiKeyServiceProvider",
    "AuditServiceProvider",
    "AuthServiceProvider",
    "BundleServiceProvider",
    "ConfigServiceProvider",
    "EndpointServiceProvider",
    "RedisProvider",
    "ServerServiceProvider",
    "SessionFactoryProvider",
    "SettingsProvider",
    "UnitOfWorkProvider",
    "UpstreamOAuthConfigServiceProvider",
    "UserServiceProvider",
    "get_admin_session_service",
    "get_api_key_service",
    "get_app_settings",
    "get_audit_service",
    "get_auth_service",
    "get_bundle_service",
    "get_config_service",
    "get_endpoint_service",
    "get_redis",
    "get_server_service",
    "get_session_factory",
    "get_unit_of_work",
    "get_upstream_oauth_config_service",
    "get_user_service",
]
