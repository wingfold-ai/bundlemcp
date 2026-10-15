"""Add the browser origins each endpoint allows from another site.

Existing endpoints get the default for their auth modes: an open endpoint
(auth modes exactly ``none``) allows no other site, every other endpoint any,
which is what it did before. The previous release ignores the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_endpoints = sa.table(
    "endpoints",
    sa.column("id", sa.Uuid()),
    sa.column("auth_modes", sa.JSON()),
    sa.column("allowed_origins", sa.JSON()),
)


def upgrade() -> None:
    op.add_column("endpoints", sa.Column("allowed_origins", sa.JSON(), nullable=True))
    bind = op.get_bind()
    for row in bind.execute(sa.select(_endpoints.c.id, _endpoints.c.auth_modes)).all():
        allowed = [] if set(row.auth_modes or []) == {"none"} else ["*"]
        bind.execute(
            _endpoints.update().where(_endpoints.c.id == row.id).values(allowed_origins=allowed)
        )


def downgrade() -> None:
    op.drop_column("endpoints", "allowed_origins")
