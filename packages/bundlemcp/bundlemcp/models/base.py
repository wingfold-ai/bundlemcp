"""Shared constants and column factories for the entity models.

Entity classes live one-per-file alongside this module. Name rules are
enforced on the API DTO layer and by Postgres CHECK constraints in the initial
migration; table models stay validation-free because SQLModel skips validators
for table=True classes.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column

from bundlemcp.models.utc_datetime import UtcDateTime

NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"
# Server names additionally must not contain "__" (DOM-4, BND-2).
RESERVED_ENDPOINT_NAMES = {
    "api",
    "oauth",
    ".well-known",
    "healthz",
    "readyz",
    "metrics",
    "docs",
    "login",
    "consent",
    "static",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ts(**kwargs: Any) -> Any:
    """Timezone-aware timestamp column."""
    return Column(UtcDateTime, **kwargs)
