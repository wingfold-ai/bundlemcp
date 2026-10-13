from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.curation_filter import CurationFilter
from bundlemcp.domain.bundles.override_stage import OverrideStage
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.bundles.profile_stage import ProfileStage
from bundlemcp.domain.bundles.tool_stage import ToolStage
from bundlemcp.domain.endpoints.profiles.endpoint_profile_preset import EndpointProfilePreset
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool


class ToolPipeline(BaseModel):
    """The ordered stages that turn a cached upstream tool into the tool an endpoint serves.

    Its output is the one tool set behind both ``tools/list`` and ``tools/call``,
    so a stage that drops a tool drops it from both.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    stages: tuple[ToolStage, ...] = Field(description="Applied in order; a None result stops")

    @classmethod
    def for_profile(cls, preset: EndpointProfilePreset) -> "ToolPipeline":
        """Curation filter, then the profile, then the per-tool overrides, which win."""
        return cls(stages=(CurationFilter(), ProfileStage(preset=preset), OverrideStage()))

    def present(
        self, server: McpServer, tool: Tool, curation: BundleTool | None
    ) -> PresentedTool | None:
        """The tool as the endpoint shows it, or None when a stage drops it."""
        current: PresentedTool | None = PresentedTool(
            presented_name=PresentedName.for_tool(server.name, tool.name, None),
            server=server,
            tool=tool,
            title=tool.title,
            description=tool.description,
            input_schema=tool.input_schema,
            annotations=tool.annotations,
        )
        for stage in self.stages:
            if current is None:
                return None
            current = stage.apply(current, curation)
        return current
