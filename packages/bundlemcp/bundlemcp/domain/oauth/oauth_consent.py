import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.shared.clock import utcnow


class OAuthConsent(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the consent")
    user_id: uuid.UUID = Field(
        description="User who granted it",
    )
    client_id: str = Field(
        description="Client it was granted to",
    )
    endpoint_id: uuid.UUID = Field(
        description="Endpoint it covers",
    )
    granted_at: datetime = Field(default_factory=utcnow, description="When the user granted it")
    revoked_at: datetime | None = Field(
        default=None,
        description="When it was withdrawn. While null the consent stands and the consent "
        "screen is skipped",
    )
