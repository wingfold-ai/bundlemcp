"""Rename the endpoint profiles for what they change.

Rewrites the profile stored on each endpoint: ``claude`` becomes ``oauth_only``
and ``chatgpt`` becomes ``write_as_read``. The column is a plain string, so
only the data changes.

Unlike the other revisions, this one is not readable by the previous release:
an old replica fails to validate a rewritten row. Stop the old replicas before
running it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = {"claude": "oauth_only", "chatgpt": "write_as_read"}

_endpoints = sa.table("endpoints", sa.column("profile", sa.String()))


def _rewrite(mapping: dict[str, str]) -> None:
    for former, successor in mapping.items():
        op.execute(
            _endpoints.update().where(_endpoints.c.profile == former).values(profile=successor)
        )


def upgrade() -> None:
    _rewrite(_RENAMES)


def downgrade() -> None:
    _rewrite({successor: former for former, successor in _RENAMES.items()})
