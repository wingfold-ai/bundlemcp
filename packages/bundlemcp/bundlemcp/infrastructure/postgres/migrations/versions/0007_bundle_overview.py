"""Add bundles.overview (BND-11).

The long-form, human-facing description of a bundle shown in the catalogue.
``description`` stays what it was: the short note served to clients as the
virtual server's MCP ``instructions``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bundles", sa.Column("overview", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("bundles", "overview")
