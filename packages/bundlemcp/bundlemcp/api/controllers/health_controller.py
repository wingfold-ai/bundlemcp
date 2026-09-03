"""Liveness and readiness probes."""

from sqlalchemy import text

from bundlemcp.http import Controller
from bundlemcp.providers import RedisProvider, SessionFactoryProvider


class HealthController(Controller):
    include_in_schema = False

    def register(self) -> None:
        self.get("/healthz", self.healthz)
        self.get("/readyz", self.readyz)

    async def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    async def readyz(
        self, sessions: SessionFactoryProvider, redis: RedisProvider
    ) -> dict[str, str]:
        """Ready means both Postgres and Redis are reachable."""
        async with sessions() as db:
            await db.execute(text("SELECT 1"))
        await redis.ping()
        return {"status": "ready"}
