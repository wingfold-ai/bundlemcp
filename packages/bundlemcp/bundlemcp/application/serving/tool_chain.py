from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.application.serving.chain_stage import ChainStage
from bundlemcp.application.serving.presentation_stage import PresentationStage
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.curation_filter import CurationFilter
from bundlemcp.domain.bundles.override_stage import OverrideStage
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.bundles.profile_stage import ProfileStage
from bundlemcp.domain.bundles.stale_tool_filter import StaleToolFilter
from bundlemcp.domain.endpoints.profiles.endpoint_profile_preset import EndpointProfilePreset
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.tool import Tool


class ToolChain(BaseModel):
    """The ordered stages every listed and every called tool of an endpoint passes.

    Stale and curation filters, the endpoint's profile and the per-tool
    overrides present the tools; their output is the one tool set behind both
    ``tools/list`` and ``tools/call``. The call stages that follow (metering,
    then audit) admit each call and hear how it ended.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    stages: tuple[ChainStage, ...] = Field(description="In order; see the class docstring")

    @classmethod
    def for_endpoint(
        cls, preset: EndpointProfilePreset, call_stages: tuple[ChainStage, ...] = ()
    ) -> "ToolChain":
        """The chain of an endpoint with this profile; without call stages it only presents."""
        presenting = (StaleToolFilter(), CurationFilter(), ProfileStage(preset=preset))
        return cls(
            stages=(
                *(PresentationStage(stage=stage) for stage in presenting),
                # after the profile, so an explicit override wins over its rewrite
                PresentationStage(stage=OverrideStage()),
                *call_stages,
            )
        )

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
            current = stage.present(current, curation)
        return current

    async def admit(self, call: ChainCall) -> CallRefusal | None:
        """The first stage's refusal, or None when every stage lets the call through."""
        for stage in self.stages:
            refusal = await stage.admit(call)
            if refusal is not None:
                return refusal
        return None

    async def pause(self, call: ChainCall, until: float) -> None:
        for stage in self.stages:
            await stage.pause(call, until)

    async def settle(self, call: ChainCall, settlement: CallSettlement) -> None:
        for stage in self.stages:
            await stage.settle(call, settlement)
