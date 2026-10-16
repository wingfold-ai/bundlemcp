"""Make API key names unique, so a key can be addressed by its name.

Existing keys that share a name keep the oldest one's name; every later one is
renamed to ``<name>-<first 8 characters of its id>``, which is unique because
ids are. Downgrade drops the constraint and leaves the renamed keys as they are.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "uq_api_keys_name"


def upgrade() -> None:
    conn = op.get_bind()
    keys = sa.table(
        "api_keys",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("created_at"),
    )
    rows = conn.execute(sa.select(keys.c.id, keys.c.name).order_by(keys.c.created_at, keys.c.id))
    seen: set[str] = set()
    for key_id, name in rows.all():
        if name not in seen:
            seen.add(name)
            continue
        renamed = f"{name}-{str(key_id).replace('-', '')[:8]}"
        conn.execute(sa.update(keys).where(keys.c.id == key_id).values(name=renamed))
        seen.add(renamed)
    with op.batch_alter_table("api_keys") as batch:
        batch.create_unique_constraint(CONSTRAINT, ["name"])


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_constraint(CONSTRAINT, type_="unique")
