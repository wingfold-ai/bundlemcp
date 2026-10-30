"""Exclusive per-server locks that last as long as one transaction."""

import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Postgres releases a transaction-level advisory lock itself on commit, rollback or a
# dropped connection, and every replica shares the database, so the lock holds fleet-wide.
ADVISORY_XACT_LOCK = text("SELECT pg_advisory_xact_lock(:key)")


def advisory_key(server_id: uuid.UUID) -> int:
    """The signed 64-bit advisory-lock key of one server.

    Two servers that happened to share a key would only wait for each other.
    """
    return int.from_bytes(server_id.bytes[:8], "big", signed=True)


class ServerLocks:
    """Takes per-server locks for the units of work of one session factory.

    On Postgres a lock is a transaction-level advisory lock. Any other database is
    the single-process sqlite the hermetic tests use, which has no lock a second
    transaction could wait on, so a process-local lock per server stands in; the
    unit of work releases it when its transaction ends.
    """

    def __init__(self) -> None:
        self._local: dict[uuid.UUID, asyncio.Lock] = {}

    async def acquire(self, session: AsyncSession, server_id: uuid.UUID) -> asyncio.Lock | None:
        """Wait for and take the server's lock; the local lock to release later, if any."""
        if session.bind.dialect.name == "postgresql":
            await session.execute(ADVISORY_XACT_LOCK, {"key": advisory_key(server_id)})
            return None
        lock = self._local.setdefault(server_id, asyncio.Lock())
        await lock.acquire()
        return lock
