import uuid

from pydantic import BaseModel


class BundleToolRead(BaseModel):
    """A member server's tool with this bundle's curation applied."""

    tool_id: uuid.UUID
    server_name: str
    name: str  # upstream tool name
    title: str | None
    description: str | None
    member_enabled: bool  # the owning server's membership toggle
    enabled: bool  # per-bundle tool toggle (default true without curation)
    presented_name: str  # override_name or "<server>__<tool>"
    override_name: str | None
    override_title: str | None
    override_description: str | None
