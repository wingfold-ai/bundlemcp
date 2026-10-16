"""Cache members' prompts and resources for curation, and their per-bundle curation.

Expand-only: two new tables. The cache fills on each server's next discovery and
curation starts empty; the previous release ignores both tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "server_id",
            sa.Uuid(),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("entry_hash", sa.String(), nullable=False),
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("server_id", "kind", "key", name="uq_member_entries_server_kind_key"),
    )
    op.create_index("ix_member_entries_server_id", "member_entries", ["server_id"])
    op.create_table(
        "bundle_member_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "bundle_id", sa.Uuid(), sa.ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "entry_id",
            sa.Uuid(),
            sa.ForeignKey("member_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("override_title", sa.String(), nullable=True),
        sa.Column("override_description", sa.String(), nullable=True),
        sa.UniqueConstraint("bundle_id", "entry_id", name="uq_bundle_member_entries_pair"),
    )
    op.create_index("ix_bundle_member_entries_bundle_id", "bundle_member_entries", ["bundle_id"])
    op.create_index("ix_bundle_member_entries_entry_id", "bundle_member_entries", ["entry_id"])


def downgrade() -> None:
    op.drop_table("bundle_member_entries")
    op.drop_table("member_entries")
