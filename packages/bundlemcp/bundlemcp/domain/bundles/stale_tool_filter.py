from pydantic import BaseModel, ConfigDict

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool


class StaleToolFilter(BaseModel):
    """Drops a tool its server no longer lists, keeping its curation for when it returns."""

    model_config = ConfigDict(frozen=True)

    def apply(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        if tool.tool.is_stale:
            return None
        return tool
