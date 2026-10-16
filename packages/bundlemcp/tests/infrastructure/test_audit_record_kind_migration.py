"""The migration that lets the audit log hold management actions (OPS-18)."""

import importlib
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

revision = importlib.import_module(
    "bundlemcp.infrastructure.postgres.migrations.versions.0014_audit_record_kind"
)


def _run(conn: sa.Connection, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_ops18_upgrade_marks_existing_records_as_tool_calls_and_downgrade_drops_columns():
    """OPS-18: rows written before the upgrade read as tool calls with no action."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE audit_records (id CHAR(32) PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO audit_records VALUES (:id)"), {"id": uuid.uuid4().hex})

        _run(conn, revision.upgrade)
        stored = conn.execute(sa.text("SELECT kind, action FROM audit_records")).all()
        assert [tuple(row) for row in stored] == [("tool_call", None)]
        # an insert that predates the column still lands as a tool call
        conn.execute(sa.text("INSERT INTO audit_records (id) VALUES (:id)"), {"id": "x"})
        kinds = conn.execute(sa.text("SELECT DISTINCT kind FROM audit_records")).scalars().all()
        assert kinds == ["tool_call"]

        _run(conn, revision.downgrade)
        columns = {c["name"] for c in sa.inspect(conn).get_columns("audit_records")}
        assert columns == {"id"}
