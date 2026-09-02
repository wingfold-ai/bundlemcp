from pydantic import BaseModel, Field


class OidcClaims(BaseModel):
    """The claims taken from a verified identity token."""

    issuer: str = Field(description="Issuer that signed the token")
    sub: str = Field(description="Stable subject identifier for the user at that issuer")
    email: str | None = Field(default=None, description="Email claim, when the issuer sent one")
    name: str | None = Field(default=None, description="Display name claim, when present")
    groups: list[str] = Field(
        default=[], description="Group claims, when the issuer is configured to send them"
    )
