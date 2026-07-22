from dataclasses import dataclass

from bundlemcp.gateway.composition.presented_tool import PresentedTool
from bundlemcp.models import Bundle, Endpoint, McpServer


@dataclass
class BundleView:
    endpoint: Endpoint
    bundle: Bundle
    servers: dict[str, McpServer]  # by name, enabled members only
    tools: list[PresentedTool]  # enabled tools, curated + profile-transformed

    def resolve(self, presented_name: str) -> PresentedTool | None:
        """Match override names first, then fall back to first-`__` prefix parsing."""
        for pt in self.tools:
            if pt.presented_name == presented_name:
                return pt
        return None
