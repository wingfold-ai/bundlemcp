from pydantic import BaseModel, ConfigDict, Field


class OidcLoginState(BaseModel):
    """What a login must remember between the redirect to the issuer and the callback."""

    model_config = ConfigDict(frozen=True)

    nonce: str = Field(description="Nonce the returned identity token must echo")
    code_verifier: str = Field(
        repr=False, description="PKCE verifier the code exchange must present"
    )
    next_url: str = Field(description="Where the browser goes once signed in")
    browser_binding_hash: str = Field(
        repr=False,
        description=(
            "Hash of the random value the starting browser holds in its login binding cookie; "
            "the callback must present the value whose hash matches"
        ),
    )
