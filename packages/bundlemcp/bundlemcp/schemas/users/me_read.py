import uuid

from pydantic import BaseModel


class MeRead(BaseModel):
    """The caller's own identity: session user (admin or not) or service key."""

    kind: str  # "admin" | "user" | "service"
    user_id: uuid.UUID | None = None
    email: str | None = None
    display_name: str | None = None
    is_admin: bool = False
    api_key_id: uuid.UUID | None = None
