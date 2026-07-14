import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow
from bundlemcp.models.endpoint_profile import EndpointProfile


class Endpoint(SQLModel, table=True):
    __tablename__ = "endpoints"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)  # public URL segment (EP-1)
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True)
    )
    profile: str = Field(default=EndpointProfile.DEFAULT)
    auth_modes: list[str] = Field(default_factory=lambda: ["api_key"], sa_column=Column(JSON))
    rate_limit: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts(onupdate=utcnow))
