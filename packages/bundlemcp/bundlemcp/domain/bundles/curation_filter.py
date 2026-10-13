from pydantic import BaseModel, ConfigDict

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool


class CurationFilter(BaseModel):
    """Drops a tool the bundle has disabled, before any later stage sees it."""

    model_config = ConfigDict(frozen=True)

    def apply(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        if curation is not None and not curation.enabled:
            return None
        return tool
