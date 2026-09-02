import uuid

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    """A user provisioned from the identity provider at login."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Identifier of the user")
    email: str | None = Field(description="Email claim from the identity provider, if it sent one")
    display_name: str | None = Field(description="Display name from the identity provider")
    is_admin: bool = Field(
        description="Whether the user held admin rights at their most recent login"
    )
    is_active: bool = Field(
        description="Whether the user may authenticate; deactivating also ends their sessions"
    )
