"""Store members' prompt, resource and resource-template listings for serving.

Expand-only: a new table and a server column with a default. The listings fill on
each server's next discovery, and until then the lists are fetched live as
before; the previous release ignores both.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_listings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "server_id",
            sa.Uuid(),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.Column("cache_scope", sa.String(), nullable=True),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("listing_hash", sa.String(), nullable=False),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("server_id", "kind", name="uq_member_listings_server_kind"),
    )
    op.create_index("ix_member_listings_server_id", "member_listings", ["server_id"])
    op.add_column(
        "mcp_servers",
        sa.Column("listing_snapshot", sa.String(), nullable=False, server_default="auto"),
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "listing_snapshot")
    op.drop_table("member_listings")
