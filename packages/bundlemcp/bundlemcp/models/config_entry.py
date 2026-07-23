from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class ConfigEntry(SQLModel, table=True):
    """Runtime-tunable key/value settings."""

    __tablename__ = "config_entries"

    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))
