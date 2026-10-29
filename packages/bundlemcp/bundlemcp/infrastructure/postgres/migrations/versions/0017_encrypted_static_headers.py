"""Give servers a column for their static header values encrypted at rest.

Expand-only: one nullable column. The gateway fills it when it writes a server with
an encryption key configured, and its background re-encryption pass seals rows still
holding plaintext; the previous release ignores the column and keeps reading the
plaintext one.

Downgrade drops the column, and with it every header value stored encrypted: those
servers must have their headers entered again, or a backup restored.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mcp_servers", sa.Column("static_headers_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mcp_servers", "static_headers_encrypted")
