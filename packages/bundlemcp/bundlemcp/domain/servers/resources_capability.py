from pydantic import Field

from bundlemcp.domain.servers.list_changed_capability import ListChangedCapability


class ResourcesCapability(ListChangedCapability):
    """The resources capability: list changes, and updates of subscribed resources."""

    subscribe: bool | None = Field(
        default=None,
        description="Whether the server sends updates of resources a client subscribed to; "
        "None when unsaid",
    )
