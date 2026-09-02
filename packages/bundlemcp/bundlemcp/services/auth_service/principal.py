from pydantic import BaseModel, Field


class Principal(BaseModel):
    """The authenticated management-API caller: an admin user or a service key."""

    kind: str = Field(description="Which credential authenticated the call: 'admin' or 'service'")
    user_id: str | None = Field(
        default=None, description="Admin user behind the session; None for service keys"
    )
    api_key_id: str | None = Field(
        default=None, description="Service key used; None for admin sessions"
    )
