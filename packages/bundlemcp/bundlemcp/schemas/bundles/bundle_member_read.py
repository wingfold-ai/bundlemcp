import uuid

from pydantic import BaseModel


class BundleMemberRead(BaseModel):
    """A server's membership in a bundle."""

    server_id: uuid.UUID
    server_name: str
    server_url: str
    health_status: str
    enabled: bool
