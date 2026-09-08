import uuid
from datetime import datetime

from pydantic import Field

from bundlemcp.application.schemas.common.entity_read import EntityRead


class ConsentRead(EntityRead):
    """A user's standing consent for one OAuth client on one endpoint."""

    id: uuid.UUID = Field(description="Identifier of the consent record")
    client_id: str = Field(description="OAuth client the consent was granted to")
    endpoint_id: uuid.UUID = Field(description="Endpoint the consent covers")
    granted_at: datetime = Field(description="When the user granted it")
