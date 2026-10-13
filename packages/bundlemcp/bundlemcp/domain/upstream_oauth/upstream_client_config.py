from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant

# Keys the gateway keeps beside the authorization server's endpoints in a client's metadata.
IDENTIFICATION_KEY = "identification"
GRANT_KEY = "grant_type"
STEP_UP_KEY = "step_up_scopes"


class UpstreamClientConfig(BaseModel):
    """The client this gateway uses at one upstream authorization server."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(description="Client id at the upstream authorization server")
    client_secret: str | None = Field(
        default=None, repr=False, description="Decrypted client secret; absent for public clients"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Authorization server endpoints as configured or previously discovered, "
        "plus how the client came to be",
    )

    @property
    def identification(self) -> ClientIdentification:
        """How this client was obtained; a record without one was stored by an admin."""
        return ClientIdentification(
            self.metadata.get(IDENTIFICATION_KEY, ClientIdentification.PREREGISTERED)
        )

    @property
    def grant(self) -> UpstreamGrant:
        return UpstreamGrant(self.metadata.get(GRANT_KEY, UpstreamGrant.AUTHORIZATION_CODE))

    # UPS-37
    @property
    def issuer(self) -> str | None:
        """The authorization server this client belongs to, when it is known."""
        return self.metadata.get("issuer")

    @property
    def step_up_scopes(self) -> list[str]:
        return list(self.metadata.get(STEP_UP_KEY) or [])

    @property
    def is_admin_stored(self) -> bool:
        """An admin entered it; the gateway never discards or replaces it on its own."""
        return self.identification == ClientIdentification.PREREGISTERED
