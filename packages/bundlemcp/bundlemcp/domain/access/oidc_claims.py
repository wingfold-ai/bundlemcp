from typing import Any

from pydantic import BaseModel, Field


class OidcClaims(BaseModel):
    """The claims taken from a verified identity token."""

    issuer: str = Field(description="Issuer that signed the token")
    sub: str = Field(description="Stable subject identifier for the user at that issuer")
    email: str | None = Field(default=None, description="Email claim, when the issuer sent one")
    email_verified: bool = Field(
        default=False,
        description="Whether the issuer vouches that the email belongs to the user; false when it "
        "did not say",
    )
    name: str | None = Field(default=None, description="Display name claim, when present")
    claims: dict[str, Any] = Field(
        default_factory=dict,
        description="Every claim of the verified token, for rules that name a claim by "
        "configuration, such as the admin claim",
    )
