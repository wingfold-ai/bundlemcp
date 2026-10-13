"""Add mcp_servers.connection_state (UPS-12).

What the last probe found out about the upstream — ready, a refusal naming
OAuth, a refusal wanting another credential, not an MCP endpoint, unreachable
— classified from its HTTP response. Existing servers start as ``unknown``
and are classified by their next probe.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column(
            "connection_state", sa.String(), nullable=False, server_default=sa.text("'unknown'")
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "connection_state")
