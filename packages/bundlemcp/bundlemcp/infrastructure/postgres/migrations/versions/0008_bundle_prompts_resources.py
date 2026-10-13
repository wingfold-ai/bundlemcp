"""Add bundle_prompts and bundle_resources (BND-18, BND-23).

Prompts and resources authored on a bundle and served by the gateway itself.
Both belong to their bundle and go with it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROMPT_NAME_RE = "^[a-zA-Z0-9_-]+$"
_RESOURCE_NAME_RE = "^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_.-]+)*$"


def upgrade() -> None:
    op.create_table(
        "bundle_prompts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "name", name="uq_bundle_prompts_name"),
    )
    op.create_index(
        op.f("ix_bundle_prompts_bundle_id"), "bundle_prompts", ["bundle_id"], unique=False
    )
    op.create_table(
        "bundle_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "name", name="uq_bundle_resources_name"),
    )
    op.create_index(
        op.f("ix_bundle_resources_bundle_id"), "bundle_resources", ["bundle_id"], unique=False
    )
    if op.get_bind().dialect.name == "postgresql":  # BND-19, BND-23
        op.create_check_constraint(
            "ck_bundle_prompts_name",
            "bundle_prompts",
            sa.text(f"name ~ '{_PROMPT_NAME_RE}' AND name NOT LIKE '%\\_\\_%'"),
        )
        op.create_check_constraint(
            "ck_bundle_resources_name",
            "bundle_resources",
            sa.text(f"name ~ '{_RESOURCE_NAME_RE}'"),
        )


def downgrade() -> None:
    op.drop_table("bundle_resources")
    op.drop_table("bundle_prompts")
