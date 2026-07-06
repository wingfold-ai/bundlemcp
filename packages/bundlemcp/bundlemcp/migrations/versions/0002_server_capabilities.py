"""Add mcp_servers.capabilities (advertised-capability snapshot, DISC-6).

Captured from the upstream initialize result at discovery; the source for
PROT-11 capability aggregation.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0001 creates tables from the live SQLModel metadata, so a fresh database
    # already carries this column — only pre-0002 databases need the ALTER.
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("mcp_servers")}
    if "capabilities" in columns:
        return
    op.add_column(
        "mcp_servers",
        sa.Column(
            "capabilities",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "capabilities")
