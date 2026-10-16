"""Whether each store answers right now, for the metrics' store-health gauge."""

import asyncio

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# a scrape must not hang on a store that does not answer
CHECK_TIMEOUT_SECONDS = 2.0


class StoreHealth:
    """Postgres and Valkey checked separately, each within a short timeout; never raises."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self._sessions = sessions
        self._redis = redis

    async def check(self) -> dict[str, bool]:
        return {"postgres": await self._postgres(), "valkey": await self._valkey()}

    async def _postgres(self) -> bool:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                async with self._sessions() as db:
                    await db.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def _valkey(self) -> bool:
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
                await self._redis.ping()
            return True
        except Exception:
            return False
