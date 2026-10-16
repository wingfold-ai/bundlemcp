from datetime import datetime
from typing import Protocol, runtime_checkable

from bundlemcp.domain.sessions.session_lifetime import SessionLifetime
from bundlemcp.domain.sessions.session_record import SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding


@runtime_checkable
class SessionStore(Protocol):
    """Handshake-era MCP sessions, shared by every replica."""

    async def create(self, record: SessionRecord, lifetime: SessionLifetime) -> None: ...

    async def load(self, session_id: str) -> SessionRecord | None:
        """The record, or None when unknown, expired or written by another build."""
        ...

    async def touch(self, session_id: str, lifetime: SessionLifetime) -> None:
        """Record activity now and restart the idle lifetime; any activity counts."""
        ...

    async def delete(self, session_id: str) -> None: ...

    async def idle_since(self, cutoff: datetime, *, limit: int) -> list[str]:
        """Up to ``limit`` ids of sessions with no activity since ``cutoff``, oldest first."""
        ...

    async def set_binding(self, session_id: str, binding: UpstreamBinding) -> SessionRecord | None:
        """Atomically add or replace one upstream binding; None when the session is gone."""
        ...

    async def set_log_level(self, session_id: str, level: str) -> SessionRecord | None:
        """Atomically record the log level the client asked for; None when the session is gone."""
        ...
