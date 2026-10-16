from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.bundle import Bundle
from bundlemcp.domain.bundles.member_entry_curation import MemberEntryCuration
from bundlemcp.domain.bundles.member_entry_ref import MemberEntryRef
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.bundles.prompt_listing import PromptListing
from bundlemcp.domain.bundles.resource_listing import ResourceListing
from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.servers.mcp_server import McpServer


class BundleView(BaseModel):
    """Everything needed to serve one endpoint, resolved from the database once."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    endpoint: Endpoint = Field(description="Endpoint being served, with its auth and rate limits")
    bundle: Bundle = Field(description="Bundle the endpoint exposes")
    servers: dict[str, McpServer] = Field(
        description="Enabled member servers, keyed by server name, in member order"
    )
    tools: list[PresentedTool] = Field(
        description="Enabled tools as presented to the client, curated and transformed"
    )
    prompts: list[PromptListing] = Field(
        default_factory=list,
        description="The bundle's own prompts in name order, without their messages",
    )
    resources: list[ResourceListing] = Field(
        default_factory=list,
        description="The bundle's own resources in name order, without their content",
    )
    member_curations: dict[MemberEntryRef, MemberEntryCuration] = Field(
        default_factory=dict,
        description="How the bundle curates its members' prompts and resources; an entry not "
        "here is served unchanged",
    )

    def resolve(self, presented_name: str) -> PresentedTool | None:
        """Match override names first, then fall back to first-`__` prefix parsing."""
        for pt in self.tools:
            if pt.presented_name == presented_name:
                return pt
        return None

    def prompt(self, name: str) -> PromptListing | None:
        """The bundle's own prompt with this name, or None."""
        return next((prompt for prompt in self.prompts if prompt.name == name), None)

    def resource(self, name: str) -> ResourceListing | None:
        """The bundle's own resource with this name, or None."""
        return next((resource for resource in self.resources if resource.name == name), None)

    def member_curation(self, ref: MemberEntryRef) -> MemberEntryCuration | None:
        """How the bundle presents one member prompt or resource; None to serve it unchanged."""
        return self.member_curations.get(ref)

    def serves_member_entry(self, ref: MemberEntryRef) -> bool:
        """Whether the bundle lists and fetches this member prompt or resource at all."""
        curation = self.member_curations.get(ref)
        return curation is None or curation.enabled
