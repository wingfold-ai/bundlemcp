"""Expiring handshake-era sessions that have been idle past their lifetime."""

from datetime import timedelta

import structlog

from bundlemcp.application.contracts.live_state.session_store import SessionStore
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.shared.clock import Clock

log = structlog.get_logger(__name__)

BATCH_SIZE = 100


class SessionSweeper:
    """Removes every session with no activity for longer than ``session_lifetime``.

    A session is checked against its own record before it is removed, so one
    that became active again after it was indexed survives. Ids whose record is
    already gone (the store's TTL removed it) leave the index too. A lifetime of
    0 means sessions never expire, and nothing is swept.
    """

    def __init__(self, sessions: SessionStore, runtime_config: RuntimeConfig, clock: Clock) -> None:
        self._sessions = sessions
        self._runtime_config = runtime_config
        self._clock = clock

    async def sweep(self) -> int:
        """Expire every idle session; returns how many this sweep expired."""
        lifetime = await self._runtime_config.session_lifetime()
        if not lifetime.expires:
            return 0
        cutoff = self._clock.now() - timedelta(seconds=lifetime.seconds)
        expired = 0
        while True:
            ids = await self._sessions.idle_since(cutoff, limit=BATCH_SIZE)
            for session_id in ids:
                record = await self._sessions.load(session_id)
                if record is not None and record.last_active_at > cutoff:
                    continue  # active again since it was indexed
                await self._sessions.delete(session_id)
                if record is not None:
                    expired += 1
                    idle = self._clock.now() - record.last_active_at
                    log.info(
                        "session.expired",
                        endpoint=record.endpoint_name,
                        idle_seconds=int(idle.total_seconds()),
                    )
            if len(ids) < BATCH_SIZE:
                return expired
