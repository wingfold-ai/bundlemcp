"""Resolving a browser session cookie to the user behind it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.models import User
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
