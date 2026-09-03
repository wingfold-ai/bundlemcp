"""Resolving a browser session cookie to the user behind it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.models import User
from bundlemcp.services.auth_service.principal import Principal
from bundlemcp.services.auth_service.principal_kind import PrincipalKind
from bundlemcp.store import Repository
from bundlemcp.store.admin_sessions import AdminSessionStore


class AdminSessionService:
    def __init__(self, db: AsyncSession, admin_sessions: AdminSessionStore) -> None:
        self._users = Repository(db, User)
        self._admin_sessions = admin_sessions

    async def session_user(self, session_id: str | None) -> User | None:
        """Resolve a browser session to its active user, admin or not.

        is_active/is_admin are re-checked against the database so deactivation and
        demotion take effect immediately, not at session expiry.
        """
        if not session_id:
            return None
        session = await self._admin_sessions.load(session_id)
        if session is None:
            return None
        user = await self._users.get(uuid.UUID(session.user_id))
        if user is None or not user.is_active:
            return None
        return user

    async def admin_principal(self, session_id: str | None) -> Principal | None:
        """Resolve a browser session to an admin Principal.

        The caller still owns the CSRF origin check on mutating requests.
        """
        user = await self.session_user(session_id)
        if user is None or not user.is_admin:
            return None
        return Principal(kind=PrincipalKind.ADMIN, user_id=str(user.id))
