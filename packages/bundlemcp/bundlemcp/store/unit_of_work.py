"""One transaction, and the invalidation events that must follow it."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.store.invalidation.invalidation_event import InvalidationEvent
from bundlemcp.store.invalidation.publish_invalidation import publish_invalidation


class UnitOfWork:
    """A database session whose commit also announces what changed.

    Services stage writes and queue the invalidation events those writes imply;
    ``commit`` writes the transaction and only then publishes the events, so a
    replica can never learn about a change that was rolled back. Inside an
    ``atomic`` scope, inner commits become flushes and the scope's exit commits
    everything at once, which is how a bootstrap document lands all or nothing.
    """

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._redis = redis
        self._pending: list[InvalidationEvent] = []
        self._atomic_depth = 0

    @property
    def session(self) -> AsyncSession:
        return self._session

    def invalidate(self, event: InvalidationEvent) -> None:
        """Queue an event to publish once the enclosing commit succeeds."""
        self._pending.append(event)

    async def commit(self) -> None:
        if self._atomic_depth:
            await self._session.flush()
            return
        await self._session.commit()
        await self._publish_pending()

    async def rollback(self) -> None:
        self._pending.clear()
        await self._session.rollback()

    @asynccontextmanager
    async def atomic(self) -> AsyncIterator[None]:
        """Defer every commit inside the block to the block's successful exit."""
        self._atomic_depth += 1
        try:
            yield
        except BaseException:
            self._atomic_depth -= 1
            if not self._atomic_depth:
                await self.rollback()
            raise
        self._atomic_depth -= 1
        if not self._atomic_depth:
            await self.commit()

    async def _publish_pending(self) -> None:
        events, self._pending = self._pending, []
        await asyncio.gather(*(publish_invalidation(self._redis, event) for event in events))


class UnitOfWorkFactory:
    """Opens a fresh unit of work per request, background task or bootstrap run."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self._sessions = sessions
        self._redis = redis

    @asynccontextmanager
    async def open(self) -> AsyncIterator[UnitOfWork]:
        async with self._sessions() as session:
            yield UnitOfWork(session, self._redis)
