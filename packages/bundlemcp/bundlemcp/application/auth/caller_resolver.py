"""Resolving whoever a management request presents: a browser session or an API key."""

from bundlemcp.application.auth.admin_session_service import AdminSessionService
from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.application.contracts.live_state.admin_session_store import AdminSessionStore
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.user import User
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class CallerResolver:
    """A browser session wins over an API key; the edge decides what each may do.

    The management API and the identity route both need the same answer to
    "who is calling?" and used to compute it separately. This is the one
    place the cookie-then-key precedence is written.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        admin_sessions: AdminSessionStore,
        *,
        clock: Clock,
        hasher: SecretHasher,
    ) -> None:
        self._sessions = AdminSessionService(uow, admin_sessions)
        self._auth = AuthService(uow, clock=clock, hasher=hasher)

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
