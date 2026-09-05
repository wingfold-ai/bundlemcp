"""Add mcp_servers.protocol_mode and mcp_servers.protocol_version (SRV-10).

``protocol_mode`` is how the gateway negotiates the MCP revision with the
upstream; ``protocol_version`` records the revision negotiated at the last
successful probe.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0001 creates tables from the live SQLModel metadata, so a fresh database
    # already carries these columns — only pre-0003 databases need the ALTERs.
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("mcp_servers")}
    if "protocol_mode" not in columns:
        op.add_column(
            "mcp_servers",
            sa.Column(
                "protocol_mode", sa.String(), nullable=False, server_default=sa.text("'auto'")
            ),
        )
    if "protocol_version" not in columns:
        op.add_column("mcp_servers", sa.Column("protocol_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("mcp_servers", "protocol_version")
    op.drop_column("mcp_servers", "protocol_mode")
