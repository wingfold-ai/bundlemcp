from pydantic import Field

from bundlemcp.domain.servers.capability_object import CapabilityObject
from bundlemcp.domain.servers.list_changed_capability import ListChangedCapability
from bundlemcp.domain.servers.open_capability import OpenCapability
from bundlemcp.domain.servers.resources_capability import ResourcesCapability
from bundlemcp.domain.servers.server_capability import ServerCapability

ANNOUNCED = ListChangedCapability(listChanged=True)


class ServerCapabilities(CapabilityObject):
    """What an MCP server advertises at initialize, or what a bundle advertises in turn.

    A member is None exactly when its key was absent: an empty object still
    advertises the capability. Every other key (``experimental``, extensions)
    is kept as it came, so the snapshot serialises back unchanged.
    """

    tools: ListChangedCapability | None = Field(
        default=None, description="The tools capability, when advertised"
    )
    prompts: ListChangedCapability | None = Field(
        default=None, description="The prompts capability, when advertised"
    )
    resources: ResourcesCapability | None = Field(
        default=None, description="The resources capability, when advertised"
    )
    completions: OpenCapability | None = Field(
        default=None, description="The completions capability, when advertised"
    )
    logging: OpenCapability | None = Field(
        default=None, description="The logging capability, when advertised"
    )

    @classmethod
    def of_bundle_content(
        cls, *, prompts: bool, resources: bool, completions: bool
    ) -> "ServerCapabilities":
        """What a bundle's own content offers: its prompts and resources change through the
        gateway, which announces it, and completions come from suggested argument values."""
        return cls(
            prompts=ANNOUNCED if prompts else None,
            resources=ResourcesCapability(listChanged=True) if resources else None,
            completions=OpenCapability() if completions else None,
        )

    def advertises(self, capability: ServerCapability) -> bool:
        """Whether this capability was advertised, with or without flags."""
        return getattr(self, capability.value) is not None

    @property
    def accepts_resource_subscriptions(self) -> bool:
        """The server sends updates of resources a client subscribed to."""
        return self.resources is not None and bool(self.resources.subscribe)

    @property
    def tools_list_changed(self) -> bool:
        """The server announces changes to its tool list."""
        return self.tools is not None and self.tools.announces_changes

    @property
    def prompts_list_changed(self) -> bool:
        """The server announces changes to its prompt list."""
        return self.prompts is not None and self.prompts.announces_changes

    @property
    def resources_list_changed(self) -> bool:
        """The server announces changes to its resource list."""
        return self.resources is not None and self.resources.announces_changes

    def relayable(self, notifications: bool) -> "ServerCapabilities":
        """What a bundle can advertise on this member's behalf.

        Prompts, resources, completions and logging pass on; tools never do,
        since the bundle serves its tools itself. The member's list-change and
        subscribe flags pass on only when ``notifications`` says the gateway
        relays the member's notifications to clients. No other key passes on.
        """
        return ServerCapabilities(
            prompts=(
                ListChangedCapability(
                    listChanged=_flag(notifications and self.prompts_list_changed)
                )
                if self.prompts is not None
                else None
            ),
            resources=(
                ResourcesCapability(
                    listChanged=_flag(notifications and self.resources_list_changed),
                    subscribe=_flag(notifications and self.accepts_resource_subscriptions),
                )
                if self.resources is not None
                else None
            ),
            completions=OpenCapability() if self.completions is not None else None,
            logging=OpenCapability() if self.logging is not None else None,
        )

    def union(self, other: "ServerCapabilities") -> "ServerCapabilities":
        """Every typed capability either side advertises, each flag set when either side sets
        it. Keys outside the typed members are not carried into the union."""
        return ServerCapabilities(
            tools=_either(self.tools, other.tools),
            prompts=_either(self.prompts, other.prompts),
            resources=_either_resources(self.resources, other.resources),
            completions=OpenCapability() if self.completions or other.completions else None,
            logging=OpenCapability() if self.logging or other.logging else None,
        )

    def with_tools_list_changed(self) -> "ServerCapabilities":
        """The same capabilities, with tools advertised and their list changes announced."""
        return self.model_copy(update={"tools": ANNOUNCED})


def _flag(value: bool) -> bool | None:
    """A flag as advertised: true, or left out."""
    return True if value else None


def _either(
    first: ListChangedCapability | None, second: ListChangedCapability | None
) -> ListChangedCapability | None:
    present = [side for side in (first, second) if side is not None]
    if not present:
        return None
    return ListChangedCapability(listChanged=_flag(any(side.announces_changes for side in present)))


def _either_resources(
    first: ResourcesCapability | None, second: ResourcesCapability | None
) -> ResourcesCapability | None:
    present = [side for side in (first, second) if side is not None]
    if not present:
        return None
    return ResourcesCapability(
        listChanged=_flag(any(side.announces_changes for side in present)),
        subscribe=_flag(any(bool(side.subscribe) for side in present)),
    )
