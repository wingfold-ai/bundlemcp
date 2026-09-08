import uuid
from typing import Literal

from pydantic import BaseModel, Field


class MeRead(BaseModel):
    """The caller's own identity: session user (admin or not) or service key."""

    kind: Literal["admin", "user", "service"] = Field(
        description="What authenticated this call: an admin session, a signed-in user without "
        "admin rights, or a service API key"
    )
    user_id: uuid.UUID | None = Field(
        default=None, description="The signed-in user; null for service keys"
    )
    email: str | None = Field(default=None, description="Email of the signed-in user")
    display_name: str | None = Field(default=None, description="Display name of the signed-in user")
    is_admin: bool = Field(
        default=False, description="Whether the caller may use the management API"
    )
    api_key_id: uuid.UUID | None = Field(
        default=None, description="The service key used; null for browser sessions"
    )
