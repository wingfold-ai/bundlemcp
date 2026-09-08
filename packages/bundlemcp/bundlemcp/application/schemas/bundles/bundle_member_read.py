import uuid

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.health_status import HealthStatus


class BundleMemberRead(BaseModel):
    """A server's membership in a bundle."""

    server_id: uuid.UUID = Field(description="Identifier of the member server")
    server_name: str = Field(description="Name of the member server")
    server_url: str = Field(description="Streamable HTTP URL the server is reached at")
    health_status: HealthStatus = Field(
        description="Result of the most recent probe: ok, error or unknown"
    )
    enabled: bool = Field(
        description="Whether this membership contributes tools; disabling hides them "
        "without losing their curation"
    )
