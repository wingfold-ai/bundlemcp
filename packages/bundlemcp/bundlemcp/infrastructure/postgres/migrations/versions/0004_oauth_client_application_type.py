"""Add oauth_clients.application_type (AUTH-2).

Recorded from dynamic client registration so the registration a client made
is reported back to it in full.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("oauth_clients")}
    if "application_type" not in columns:
        op.add_column("oauth_clients", sa.Column("application_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("oauth_clients", "application_type")
