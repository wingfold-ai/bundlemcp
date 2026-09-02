import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow
from bundlemcp.models.endpoint_profile import EndpointProfile


class Endpoint(SQLModel, table=True):
    __tablename__ = "endpoints"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the endpoint"
    )
    name: str = Field(  # EP-1
        unique=True,
        index=True,
        description="Unique endpoint name; it forms the public URL path segment",
    )
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True),
        description="Bundle this endpoint exposes",
    )
    profile: str = Field(
        default=EndpointProfile.DEFAULT,
        description="Client profile shaping the responses for a particular consumer",
    )
    auth_modes: list[str] = Field(
        default_factory=lambda: ["api_key"],
        sa_column=Column(JSON),
        description="Accepted credentials: oauth, api_key, or none for an open endpoint",
    )
    rate_limit: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Rate-limit configuration; null when the endpoint is unlimited",
    )
    enabled: bool = Field(
        default=True, description="Whether the endpoint currently serves requests"
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=_ts(), description="When the record was created"
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=_ts(onupdate=utcnow),
        description="When the record was last changed",
    )
