"""The ``config_entries`` table, as SQLAlchemy sees it."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class ConfigEntryRow(SQLModel, table=True):
    __tablename__ = "config_entries"

    key: str = Field(primary_key=True, description="Name of the setting")
    value: Any = Field(
        default=None,
        sa_column=Column(JSON),
        description="Stored value; its type comes from the key's declared default",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(onupdate=utcnow),
        description="When the value was last changed",
    )
