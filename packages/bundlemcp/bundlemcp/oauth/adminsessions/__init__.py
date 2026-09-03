"""Browser sessions for humans: random id in Redis, httpOnly cookie.

Max age forces periodic re-login so IdP-side changes take effect.
"""

from bundlemcp.oauth.adminsessions.admin_session import AdminSession
from bundlemcp.oauth.adminsessions.admin_session_store import (
    ADMIN_SESSION_KEY,
    DEFAULT_MAX_AGE,
    SESSION_COOKIE,
    AdminSessionStore,
)

__all__ = [
    "ADMIN_SESSION_KEY",
    "DEFAULT_MAX_AGE",
    "SESSION_COOKIE",
    "AdminSession",
    "AdminSessionStore",
]
