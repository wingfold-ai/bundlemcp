from enum import StrEnum

from bundlemcp.domain.servers.server_capability import ServerCapability


class ListingKind(StrEnum):
    """Which of a member's list methods a listing answers."""

    PROMPTS = "prompts"
    RESOURCES = "resources"
    RESOURCE_TEMPLATES = "resource_templates"

    @property
    def capability(self) -> ServerCapability:
        """The capability a server must advertise to be asked for this listing."""
        if self is ListingKind.PROMPTS:
            return ServerCapability.PROMPTS
        return ServerCapability.RESOURCES

    @property
    def key(self) -> str:
        """The wire field that identifies one entry of the listing."""
        return {
            ListingKind.PROMPTS: "name",
            ListingKind.RESOURCES: "uri",
            ListingKind.RESOURCE_TEMPLATES: "uriTemplate",
        }[self]
