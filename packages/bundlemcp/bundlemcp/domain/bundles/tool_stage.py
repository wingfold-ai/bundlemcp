from typing import Protocol, runtime_checkable

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool


@runtime_checkable
class ToolStage(Protocol):
    """One step of turning a cached upstream tool into the tool an endpoint serves."""

    def apply(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        """The tool after this step, or None to drop it from the endpoint altogether."""
        ...
