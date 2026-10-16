"""Let the audit log hold management actions beside tool calls.

Expand-only: ``kind`` defaults to ``tool_call`` on the server, so existing rows
and the previous release's inserts stay tool-call records; ``action`` is
nullable and only management records set it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_records",
        sa.Column("kind", sa.String(), nullable=False, server_default=sa.text("'tool_call'")),
    )
    op.add_column("audit_records", sa.Column("action", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("audit_records") as batch:
        batch.drop_column("action")
        batch.drop_column("kind")
