"""A timestamp column that always reads back timezone-aware."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Stores UTC and hands back aware datetimes on every backend.

    Postgres keeps the offset itself; sqlite does not, and would otherwise
    return naive values that cannot be compared with aware ones. Normalising in
    the type means no caller has to guess which kind it was given.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)


def timestamp_column(**kwargs: Any) -> Any:
    """A timezone-aware timestamp column for an entity declaration."""
    return Column(UtcDateTime, **kwargs)
