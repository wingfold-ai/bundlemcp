import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class User(BaseModel):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Stable identifier used as the subject of issued tokens",
    )
    oidc_issuer: str = Field(description="Issuer that authenticated this user")
    oidc_sub: str = Field(description="Subject identifier for this user at that issuer")
    email: str | None = Field(default=None, description="Email claim, when the issuer sent one")
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
        description="When the record was created",
    )
