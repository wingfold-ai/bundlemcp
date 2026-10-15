"""The migration that gives every endpoint its allowed browser origins (EP-24)."""

import importlib
import json
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

revision = importlib.import_module(
    "bundlemcp.infrastructure.postgres.migrations.versions.0011_endpoint_allowed_origins"
)


def _run(conn: sa.Connection, step) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        step()


def test_ep24_upgrade_keeps_todays_behaviour_for_authenticated_endpoints():
    """EP-24: an oauth or key endpoint gets ['*'], an open one [], and downgrade drops it."""
    engine = sa.create_engine("sqlite://")
    rows = {"oauth": ["oauth"], "keys": ["oauth", "api_key"], "open": ["none"]}
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE endpoints (id CHAR(32) PRIMARY KEY, name VARCHAR, auth_modes JSON)"
            )
        )
        for name, modes in rows.items():
            conn.execute(
                sa.text("INSERT INTO endpoints VALUES (:id, :name, :modes)"),
                {"id": uuid.uuid4().hex, "name": name, "modes": json.dumps(modes)},
            )

        _run(conn, revision.upgrade)
        stored = conn.execute(sa.text("SELECT name, allowed_origins FROM endpoints")).all()
        assert {name: json.loads(origins) for name, origins in stored} == {
            "oauth": ["*"],
            "keys": ["*"],
            "open": [],
        }

        _run(conn, revision.downgrade)
        columns = {c["name"] for c in sa.inspect(conn).get_columns("endpoints")}
        assert "allowed_origins" not in columns
