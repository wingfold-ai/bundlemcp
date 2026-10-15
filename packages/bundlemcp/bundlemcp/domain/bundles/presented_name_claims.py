import uuid

from pydantic import BaseModel, Field

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool


class PresentedNameClaims(BaseModel):
    """Served tools with every presented name held by exactly one of them.

    Writes refuse a name collision, but discovery cannot be refused: an
    upstream may add a tool whose prefixed name equals an existing override.
    The override keeps the name, because an admin chose it, and the
    discovered tool is not served until the clash is resolved.
    """

    kept: list[PresentedTool] = Field(description="Tools served, one per presented name")
    displaced: list[PresentedTool] = Field(
        default_factory=list,
        description="Tools not served because an override already holds their name",
    )

    @classmethod
    def settle(
        cls, tools: list[PresentedTool], curations: dict[uuid.UUID, BundleTool]
    ) -> "PresentedNameClaims":
        holders: dict[str, PresentedTool] = {}
        displaced: list[PresentedTool] = []
        for tool in tools:
            held = holders.get(tool.presented_name)
            if held is None:
                holders[tool.presented_name] = tool
            elif cls._overridden(tool, curations) and not cls._overridden(held, curations):
                holders[tool.presented_name] = tool
                displaced.append(held)
            else:
                displaced.append(tool)
        return cls(kept=list(holders.values()), displaced=displaced)

    @staticmethod
    def _overridden(tool: PresentedTool, curations: dict[uuid.UUID, BundleTool]) -> bool:
        curation = curations.get(tool.tool.id)
        return curation is not None and bool(curation.override_name)
