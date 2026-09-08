"""Readiness as the deployment defines it: Postgres and the live store both answer."""

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class StoreReadinessProbe:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self._sessions = sessions
        self._redis = redis

    async def check(self) -> None:
        async with self._sessions() as db:
            await db.execute(text("SELECT 1"))
        await self._redis.ping()
