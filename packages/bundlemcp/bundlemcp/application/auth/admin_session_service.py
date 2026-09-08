"""Resolving a browser session cookie to the user behind it."""

import uuid

from bundlemcp.application.contracts.live_state.admin_session_store import AdminSessionStore
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.user import User


class AdminSessionService:
    def __init__(self, uow: UnitOfWork, admin_sessions: AdminSessionStore) -> None:
        self._users = uow.users
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
