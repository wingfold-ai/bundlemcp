"""Add oauth_access_tokens.family_id (AUTH-4, RFC 9700 section 4.14.2).

Every pair descended from one authorization grant through refresh rotation
shares a family id, so a replayed refresh token can revoke all of them.
Existing rows become one-member families keyed by their own id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("oauth_access_tokens")}
    if "family_id" in columns:
        return
    op.add_column("oauth_access_tokens", sa.Column("family_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE oauth_access_tokens SET family_id = id")
    with op.batch_alter_table("oauth_access_tokens") as batch:
        batch.alter_column("family_id", nullable=False)
    op.create_index("ix_oauth_access_tokens_family_id", "oauth_access_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_access_tokens_family_id", table_name="oauth_access_tokens")
    with op.batch_alter_table("oauth_access_tokens") as batch:
        batch.drop_column("family_id")
