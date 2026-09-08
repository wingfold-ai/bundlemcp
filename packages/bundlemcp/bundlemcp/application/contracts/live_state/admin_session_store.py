from typing import Protocol, runtime_checkable

from bundlemcp.domain.sessions.admin_session import AdminSession


@runtime_checkable
class AdminSessionStore(Protocol):
    """Browser sessions for the management UI, kept under unguessable ids."""

    @property
    def max_age(self) -> int:
        """Seconds a session lives before the user must log in again."""
        ...

    async def create(self, session: AdminSession) -> str:
        """Store a session and return the id that retrieves it."""
        ...

    async def load(self, session_id: str) -> AdminSession | None:
        """The session behind an id; None when unknown, expired or malformed."""
        ...

    async def delete(self, session_id: str) -> None: ...
