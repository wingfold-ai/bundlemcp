"""The migration that makes API key names unique (AUTH-23)."""

import importlib
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

revision = importlib.import_module(
    "bundlemcp.infrastructure.postgres.migrations.versions.0013_unique_api_key_names"
)


def _run(conn: sa.Connection, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_auth23_duplicates_are_renamed_then_names_are_unique():
    """AUTH-23: the oldest key keeps a shared name, later ones get an id suffix; then 409-able."""
    engine = sa.create_engine("sqlite://")
    ids = [uuid.uuid4().hex for _ in range(3)]
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE api_keys (id CHAR(32) PRIMARY KEY, name VARCHAR, created_at INT)")
        )
        for order, (key_id, name) in enumerate(zip(ids, ["ci", "ci", "other"], strict=True)):
            conn.execute(
                sa.text("INSERT INTO api_keys VALUES (:id, :name, :at)"),
                {"id": key_id, "name": name, "at": order},
            )
        _run(conn, revision.upgrade)
        names = dict(conn.execute(sa.text("SELECT id, name FROM api_keys")).all())
        assert names == {ids[0]: "ci", ids[1]: f"ci-{ids[1][:8]}", ids[2]: "other"}
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(sa.text("INSERT INTO api_keys VALUES ('x', 'ci', 9)"))
        _run(conn, revision.downgrade)
        conn.execute(sa.text("INSERT INTO api_keys VALUES ('y', 'ci', 10)"))
