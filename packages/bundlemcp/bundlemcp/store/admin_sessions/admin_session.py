from pydantic import BaseModel, Field


class AdminSession(BaseModel):
    """A logged-in admin browser session, stored in Valkey under a random id."""

    user_id: str = Field(description="Identifier of the signed-in user")
    email: str | None = Field(description="Email claim from the identity provider, if it sent one")
    is_admin: bool = Field(
        description="Whether the user held admin rights at their most recent login"
    )
