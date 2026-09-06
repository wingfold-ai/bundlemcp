"""Resolving whoever a management request presents: a browser session or an API key."""

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.models import ApiKey, User
from bundlemcp.services.auth_service.admin_session_service import AdminSessionService
from bundlemcp.services.auth_service.auth_service import AuthService
from bundlemcp.store.admin_sessions import AdminSessionStore


class CallerResolver:
    """A browser session wins over an API key; the edge decides what each may do.

    The management API and the identity route both need the same answer to
    "who is calling?" and used to compute it separately. This is the one
    place the cookie-then-key precedence is written.
    """

    def __init__(self, db: AsyncSession, admin_sessions: AdminSessionStore) -> None:
        self._sessions = AdminSessionService(db, admin_sessions)
        self._auth = AuthService(db)

    async def resolve(
        self, *, session_id: str | None, authorization: str | None, x_api_key: str | None
    ) -> User | ApiKey | None:
        """The active user behind a session cookie, else the active key behind a header."""
        user = await self._sessions.session_user(session_id)
        if user is not None:
            return user
        return await self._auth.authenticate_api_key(
            authorization=authorization, x_api_key=x_api_key
        )
