"""Alembic environment — async engine, advisory-lock guarded so replicas never race."""

import asyncio
import os

import bundlemcp.models  # noqa: F401  (register all tables on the metadata)
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

config = context.config
target_metadata = SQLModel.metadata

# One well-known advisory lock id so N replicas never run migrations concurrently (DEP-4).
MIGRATION_LOCK_ID = 0x62_6D_63_70  # "bmcp"


def _database_url() -> str:
    return os.environ.get("BUNDLEMCP_DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url())
    async with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            from sqlalchemy import text

            await connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
            )
        try:
            await connection.run_sync(_run_migrations)
            await connection.commit()
        finally:
            if engine.dialect.name == "postgresql":
                from sqlalchemy import text

                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID}
                )
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
