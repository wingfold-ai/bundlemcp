"""FastAPI providers for the collaborators no single package owns.

These are app-owned dependency *providers* (not third-party dependencies): each
``get_*`` reads a process-wide collaborator that the composition root published
onto ``app.state``, or builds a request-scoped service from one, and the
``*Provider`` alias injects it into a route signature.

They live at the library level rather than under ``api/`` because both the
management-API routers and the OAuth routes consume them; a package that owns
its own collaborators exposes them from its own ``providers`` module instead
(see ``oauth/providers.py``).
"""

from bundlemcp.providers.collaborators import (
    DbProvider,
    RedisProvider,
    SessionFactoryProvider,
    SettingsProvider,
    get_app_settings,
    get_db,
    get_redis,
    get_session_factory,
)
from bundlemcp.providers.services import (
    ApiKeyServiceProvider,
    AuditServiceProvider,
    BundleServiceProvider,
    ConfigServiceProvider,
    EndpointServiceProvider,
    ServerServiceProvider,
    UserServiceProvider,
    get_api_key_service,
    get_audit_service,
    get_bundle_service,
    get_config_service,
    get_endpoint_service,
    get_server_service,
    get_user_service,
)

__all__ = [
    "ApiKeyServiceProvider",
    "AuditServiceProvider",
    "BundleServiceProvider",
    "ConfigServiceProvider",
    "DbProvider",
    "EndpointServiceProvider",
    "RedisProvider",
    "ServerServiceProvider",
    "SessionFactoryProvider",
    "SettingsProvider",
    "UserServiceProvider",
    "get_api_key_service",
    "get_app_settings",
    "get_audit_service",
    "get_bundle_service",
    "get_config_service",
    "get_db",
    "get_endpoint_service",
    "get_redis",
    "get_server_service",
    "get_session_factory",
    "get_user_service",
]
