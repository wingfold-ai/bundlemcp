from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_client_metadata import UpstreamClientMetadata
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant


class UpstreamClientConfig(BaseModel):
    """The client this gateway uses at one upstream authorization server."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(description="Client id at the upstream authorization server")
    client_secret: str | None = Field(
        default=None, repr=False, description="Decrypted client secret; absent for public clients"
    )
    metadata: UpstreamClientMetadata = Field(
        default_factory=UpstreamClientMetadata,
        description="Authorization server endpoints as configured or previously discovered, "
        "plus how the client came to be",
    )

    @property
    def identification(self) -> ClientIdentification:
        """How this client was obtained; a record without one was stored by an admin."""
        return self.metadata.identification

    @property
    def grant(self) -> UpstreamGrant:
        return self.metadata.grant

    @property
    def issuer(self) -> str | None:
        """The authorization server this client belongs to, when it is known."""
        return self.metadata.endpoints.issuer if self.metadata.endpoints is not None else None

    @property
    def step_up_scopes(self) -> list[str]:
        return list(self.metadata.step_up_scopes)

    @property
    def is_admin_stored(self) -> bool:
        """An admin entered it; the gateway never discards or replaces it on its own."""
        return self.metadata.is_admin_stored
