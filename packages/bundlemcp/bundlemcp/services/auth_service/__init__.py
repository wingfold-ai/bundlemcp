"""Framework-free authentication: credential resolution and the resulting principals."""

from bundlemcp.services.auth_service.admin_session_service import AdminSessionService
from bundlemcp.services.auth_service.auth_service import AuthService
from bundlemcp.services.auth_service.caller_resolver import CallerResolver
from bundlemcp.services.auth_service.principal import Principal
from bundlemcp.services.auth_service.principal_kind import PrincipalKind

__all__ = ["AdminSessionService", "AuthService", "CallerResolver", "Principal", "PrincipalKind"]
