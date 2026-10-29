import uuid

from pydantic import BaseModel, Field

from bundlemcp.domain.upstream_oauth.upstream_client_metadata import UpstreamClientMetadata


class UpstreamOAuthClient(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the registration")
    server_id: uuid.UUID = Field(
        description="Upstream server this client is registered with",
    )
    client_id: str | None = Field(
        default=None,
        description="Client id at the upstream authorization server; null until registered",
    )
    client_secret_encrypted: str | None = Field(
        default=None,
        description="Client secret, encrypted at rest. Never returned by the API",
    )
    metadata_: UpstreamClientMetadata = Field(
        default_factory=UpstreamClientMetadata,
        description="Endpoints discovered from the upstream authorization server, and how the "
        "client was obtained",
    )
