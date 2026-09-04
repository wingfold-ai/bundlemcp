from pydantic import BaseModel, ConfigDict, Field


class OidcLoginState(BaseModel):
    """What a login must remember between the redirect to the issuer and the callback."""

    model_config = ConfigDict(frozen=True)

    nonce: str = Field(description="Nonce the returned identity token must echo")
    next_url: str = Field(description="Where the browser goes once signed in")
