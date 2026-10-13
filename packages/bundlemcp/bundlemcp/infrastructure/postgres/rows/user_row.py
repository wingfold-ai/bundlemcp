"""The ``users`` table, as SQLAlchemy sees it."""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.infrastructure.postgres.utc_datetime import timestamp_column


class UserRow(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_sub", name="uq_users_issuer_sub"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Stable identifier used as the subject of issued tokens",
    )
    oidc_issuer: str = Field(description="Issuer that authenticated this user")
    oidc_sub: str = Field(description="Subject identifier for this user at that issuer")
    email: str | None = Field(
        default=None, index=True, description="Email claim, when the issuer sent one"
    )
    display_name: str | None = Field(
        default=None, description="Display name claim, when the issuer sent one"
    )
    is_admin: bool = Field(
        default=False,
        description="Whether the user may use the management API. Re-evaluated at every login",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the user may authenticate; deactivating also ends their sessions",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=timestamp_column(),
        description="When the record was created",
    )
