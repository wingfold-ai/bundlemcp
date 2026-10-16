"""Record each audit row's metering idempotency key, the join to the metering ledger.

Expand-only: a nullable, indexed column. Existing rows have no key, and the
previous release ignores the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_records", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_index("ix_audit_idempotency_key", "audit_records", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_audit_idempotency_key", table_name="audit_records")
    op.drop_column("audit_records", "idempotency_key")
