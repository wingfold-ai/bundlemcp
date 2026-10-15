"""The data migration that renames the stored endpoint profiles."""

import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

revision = importlib.import_module(
    "bundlemcp.infrastructure.postgres.migrations.versions.0009_rename_endpoint_profiles"
)


def _profiles(conn: sa.Connection) -> dict[str, str]:
    rows = conn.execute(sa.text("SELECT name, profile FROM endpoints ORDER BY name"))
    return {name: profile for name, profile in rows}


def _run(conn: sa.Connection, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_ep23_stored_profiles_are_renamed_and_restored():
    """Upgrading rewrites claude/chatgpt to their successors; downgrading restores them."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE endpoints (name VARCHAR PRIMARY KEY, profile VARCHAR)"))
        conn.execute(
            sa.text(
                "INSERT INTO endpoints VALUES ('a', 'claude'), ('b', 'chatgpt'), ('c', 'default')"
            )
        )

        _run(conn, revision.upgrade)
        assert _profiles(conn) == {"a": "oauth_only", "b": "write_as_read", "c": "default"}

        _run(conn, revision.downgrade)
        assert _profiles(conn) == {"a": "claude", "b": "chatgpt", "c": "default"}
