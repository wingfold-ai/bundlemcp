import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from bundlemcp.models.api_key_kind import ApiKeyKind
from bundlemcp.models.base import _ts, utcnow


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    key_hash: str = Field(unique=True, index=True)  # KEY-1
    key_prefix: str  # display only
    kind: str = Field(default=ApiKeyKind.ENDPOINT)  # KEY-2
    endpoint_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # empty = all
    is_active: bool = Field(default=True)
    last_used_at: datetime | None = Field(default=None, sa_column=_ts())
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
