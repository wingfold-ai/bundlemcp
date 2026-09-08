"""The ``oauth_consents`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class OAuthConsentRow(SQLModel, table=True):
    __tablename__ = "oauth_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", "endpoint_id", name="uq_consents_triple"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the consent"
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True),
        description="User who granted it",
    )
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE")),
        description="Client it was granted to",
    )
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE")),
        description="Endpoint it covers",
    )
    granted_at: datetime = Field(
        default_factory=utcnow, sa_column=timestamp_column(), description="When the user granted it"
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(),
        description="When it was withdrawn. While null the consent stands and the consent "
        "screen is skipped",
    )
