"""Give API keys a list of scopes.

Expand-only: one non-null JSON column defaulting to an empty list, which means a service
key may do everything, so every existing key keeps exactly its rights. The previous
release ignores the column.

Downgrade drops the column, and with it every key's limits: scoped service keys become
full service keys. Deactivate or delete scoped keys before downgrading.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "scopes")
