"""The ``endpoints`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlmodel import Field, SQLModel

from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class EndpointRow(SQLModel, table=True):
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
    profile: EndpointProfile = Field(
        default=EndpointProfile.DEFAULT,
        sa_type=String,
        description="Client profile shaping the responses for a particular consumer",
    )
    auth_modes: list[EndpointAuthMode] = Field(
        default_factory=lambda: [EndpointAuthMode.API_KEY],
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
        default_factory=utcnow,
        sa_column=timestamp_column(),
        description="When the record was created",
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(onupdate=utcnow),
        description="When the record was last changed",
    )
