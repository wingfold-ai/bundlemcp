"""Readiness as the deployment defines it: Postgres and the live store both answer."""

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.application.contracts.persistence.store_unavailable import StoreUnavailable
from bundlemcp.infrastructure.postgres.sqlalchemy_unit_of_work import is_store_outage


class StoreReadinessProbe:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis) -> None:
        self._sessions = sessions
        self._redis = redis

    async def check(self) -> None:
        try:
            async with self._sessions() as db:
                await db.execute(text("SELECT 1"))
        except Exception as exc:
            if is_store_outage(exc):
                raise StoreUnavailable(type(exc).__name__) from exc
            raise
        await self._redis.ping()
