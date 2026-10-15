from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.serving.call_refusal import CallRefusal
from bundlemcp.application.serving.call_settlement import CallSettlement
from bundlemcp.application.serving.chain_call import ChainCall
from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.bundles.tool_stage import ToolStage


class PresentationStage(BaseModel):
    """A domain tool stage in the chain: it shapes tools and lets every call through.

    The tool set it shapes is the one a call is resolved against, so a tool it
    drops is refused on call before any call stage runs.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    stage: ToolStage = Field(description="The domain rule this stage applies")

    def present(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        return self.stage.apply(tool, curation)

    async def admit(self, call: ChainCall) -> CallRefusal | None:
        return None

    async def pause(self, call: ChainCall, until: float) -> None:
        return None

    async def settle(self, call: ChainCall, settlement: CallSettlement) -> None:
        return None
