from pydantic import Field

from bundlemcp.domain.servers.capability_object import CapabilityObject


class ListChangedCapability(CapabilityObject):
    """A listing capability (tools, prompts) that may announce changes to its list."""

    list_changed: bool | None = Field(
        default=None,
        alias="listChanged",
        description="Whether the server notifies when the list changes; None when unsaid",
    )

    @property
    def announces_changes(self) -> bool:
        """The server promised a notification whenever the list changes."""
        return bool(self.list_changed)
