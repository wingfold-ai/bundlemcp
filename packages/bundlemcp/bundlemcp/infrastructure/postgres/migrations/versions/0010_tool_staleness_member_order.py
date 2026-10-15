"""Mark stale tools, record the last discovery, and order bundle members (UPS-18, UPS-19, BND-1).

A tool now records when a successful discovery stopped listing it instead of
when it was last seen, so a discovery run that changes nothing writes no tool.
The server records when it was last discovered, which is what "last seen"
means for every tool it still lists; it is backfilled from the newest
``last_seen_at`` of its tools. Existing vanished tools cannot be told apart at
migration time and become stale on the server's next successful discovery.

Bundle members gain a position, backfilled per bundle in server-name order,
which is the order they were served in before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers", sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE mcp_servers SET last_discovered_at = "
        "(SELECT max(tools.last_seen_at) FROM tools WHERE tools.server_id = mcp_servers.id)"
    )
    op.add_column("tools", sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True))
    op.drop_column("tools", "last_seen_at")

    op.add_column(
        "bundle_servers",
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(
        "UPDATE bundle_servers SET position = ranked.position FROM ("
        " SELECT bundle_servers.id AS id,"
        " row_number() OVER (PARTITION BY bundle_servers.bundle_id"
        " ORDER BY mcp_servers.name) - 1 AS position"
        " FROM bundle_servers JOIN mcp_servers ON mcp_servers.id = bundle_servers.server_id"
        ") AS ranked WHERE bundle_servers.id = ranked.id"
    )


def downgrade() -> None:
    op.drop_column("bundle_servers", "position")
    op.add_column("tools", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE tools SET last_seen_at = coalesce(tools.stale_since, "
        "(SELECT mcp_servers.last_discovered_at FROM mcp_servers "
        "WHERE mcp_servers.id = tools.server_id))"
    )
    op.drop_column("tools", "stale_since")
    op.drop_column("mcp_servers", "last_discovered_at")
