import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class Bundle(SQLModel, table=True):
    __tablename__ = "bundles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None  # served as MCP instructions (BND-1)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))
