from pydantic import BaseModel, Field


class UpstreamTokens(BaseModel):
    """A token set issued by an upstream authorization server, stored encrypted."""

    access_token: str = Field(description="Bearer token sent on upstream calls")
    refresh_token: str | None = Field(
        default=None,
        description="Token used to obtain a new access token; absent when the server issues none",
    )
    expires_in: int | None = Field(
        default=None,
        description="Lifetime of the access token in seconds, as issued",
    )
    scope: str | None = Field(default=None, description="Scopes the token was granted")
    account_hint: str | None = Field(  # UPO-5
        default=None,
        description="Masked account or email identifying which upstream account this is, "
        "so a user can tell their connections apart",
    )
