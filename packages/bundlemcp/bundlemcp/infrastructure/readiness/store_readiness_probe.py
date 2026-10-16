"""Readiness as the deployment defines it: both stores answer and the schema is current."""

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bundlemcp.application.contracts.readiness_report import CheckResult, ReadinessReport
from bundlemcp.infrastructure.postgres.shipped_migrations import ShippedMigrations

PASSED = CheckResult(ok=True)


class StoreReadinessProbe:
    """Checks Postgres, Valkey and the schema separately, catching each one's own failure.

    The schema check runs only when Postgres answers; it reads the applied
    revision from ``alembic_version`` and compares it with the head this
    release ships.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        migrations: ShippedMigrations,
    ) -> None:
        self._sessions = sessions
        self._redis = redis
        self._migrations = migrations

    async def check(self) -> ReadinessReport:
        applied: str | None = None
        try:
            async with self._sessions() as db:
                await db.execute(text("SELECT 1"))
                try:
                    applied = (
                        await db.execute(text("SELECT version_num FROM alembic_version"))
                    ).scalar_one_or_none()
                except Exception:
                    applied = None  # never migrated
            postgres = PASSED
        except Exception as exc:
            postgres = CheckResult(ok=False, reason=f"unreachable ({type(exc).__name__})")
        try:
            await self._redis.ping()
            valkey = PASSED
        except Exception as exc:
            valkey = CheckResult(ok=False, reason=f"unreachable ({type(exc).__name__})")
        if not postgres.ok:
            migrations = CheckResult(ok=False, reason="unknown while Postgres is unreachable")
        elif self._migrations.is_current(applied):
            migrations = PASSED
        else:
            migrations = CheckResult(
                ok=False,
                reason=f"schema at {applied or 'no revision'}, this release needs "
                f"{self._migrations.head}",
            )
        return ReadinessReport(postgres=postgres, valkey=valkey, migrations=migrations)
