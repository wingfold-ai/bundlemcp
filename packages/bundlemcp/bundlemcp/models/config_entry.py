from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class ConfigEntry(SQLModel, table=True):
    """Runtime-tunable key/value settings."""

    __tablename__ = "config_entries"

    key: str = Field(primary_key=True, description="Name of the setting")
    value: Any = Field(
        default=None,
        sa_column=Column(JSON),
        description="Stored value; its type comes from the key's declared default",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=_ts(onupdate=utcnow),
        description="When the value was last changed",
    )
