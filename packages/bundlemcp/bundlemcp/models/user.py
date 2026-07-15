import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts, utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_sub", name="uq_users_issuer_sub"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # the stable `sub`
    oidc_issuer: str
    oidc_sub: str
    email: str | None = Field(default=None, index=True)
    display_name: str | None = None
    is_admin: bool = Field(default=False)  # re-evaluated every login (ADM-3)
    is_active: bool = Field(default=True)  # ADM-6 deactivation
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
