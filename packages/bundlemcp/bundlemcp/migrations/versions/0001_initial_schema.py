"""Initial schema.

Creates all tables from the SQLModel metadata — the entity classes are the
single source of truth for the initial revision; later revisions are explicit
diffs. Adds Postgres-only CHECK constraints for name rules that hermetic
sqlite tests enforce at the DTO layer instead.
"""

from collections.abc import Sequence

import bundlemcp.models  # noqa: F401  (register all tables on the metadata)
import sqlalchemy as sa
from alembic import op
from sqlmodel import SQLModel

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME_RE = "^[a-zA-Z0-9_-]+$"


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind)

    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_mcp_servers_name",
            "mcp_servers",
            sa.text(f"name ~ '{_NAME_RE}' AND name NOT LIKE '%\\_\\_%'"),
        )
        op.create_check_constraint("ck_bundles_name", "bundles", sa.text(f"name ~ '{_NAME_RE}'"))
        op.create_check_constraint(
            "ck_endpoints_name", "endpoints", sa.text(f"name ~ '{_NAME_RE}'")
        )


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
