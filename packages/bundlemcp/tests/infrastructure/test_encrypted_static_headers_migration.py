"""The migration that gives servers a column for encrypted static headers (ARC-18)."""

import importlib
import json
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

revision = importlib.import_module(
    "bundlemcp.infrastructure.postgres.migrations.versions.0017_encrypted_static_headers"
)


def _run(conn: sa.Connection, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_arc18_migration_adds_column_and_keeps_plaintext():
    """ARC-18: upgrading from 0016 adds a nullable static_headers_encrypted column and leaves
    plaintext headers readable; downgrade drops the column again."""
    assert revision.down_revision == "0016"
    engine = sa.create_engine("sqlite://")
    headers = {"Authorization": "Bearer s3cret"}
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE mcp_servers (id CHAR(32) PRIMARY KEY, static_headers JSON)")
        )
        conn.execute(
            sa.text("INSERT INTO mcp_servers VALUES (:id, :headers)"),
            {"id": uuid.uuid4().hex, "headers": json.dumps(headers)},
        )

        _run(conn, revision.upgrade)
        [(stored, encrypted)] = conn.execute(
            sa.text("SELECT static_headers, static_headers_encrypted FROM mcp_servers")
        ).all()
        assert json.loads(stored) == headers
        assert encrypted is None
        [column] = [
            c
            for c in sa.inspect(conn).get_columns("mcp_servers")
            if c["name"] == "static_headers_encrypted"
        ]
        assert column["nullable"] is True

        _run(conn, revision.downgrade)
        columns = {c["name"] for c in sa.inspect(conn).get_columns("mcp_servers")}
        assert "static_headers_encrypted" not in columns
