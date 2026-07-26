"""Authentication resolution shared by the management API, the MCP edge, and
the OAuth token endpoint.

Framework-free: methods take header/cookie strings and an AsyncSession, never a
web Request, so any edge can reuse them. HTTP status policy (401 vs 403) and
CSRF checks stay with the caller.
"""

from bundlemcp.services.auth_service.auth_service import AuthService
from bundlemcp.services.auth_service.principal import Principal

__all__ = [
    "AuthService",
    "Principal",
]
