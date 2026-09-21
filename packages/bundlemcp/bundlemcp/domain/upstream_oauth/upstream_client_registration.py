from pydantic import BaseModel, ConfigDict, Field


class UpstreamClientRegistration(BaseModel):
    """The client an upstream authorization server issued this gateway at registration."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(description="Client id the authorization server assigned")
    client_secret: str | None = Field(
        default=None,
        repr=False,
        description="Client secret, when the server issued one despite the public-client request",
    )
