from typing import Any

from pydantic import BaseModel, ConfigDict

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_name import PresentedName
from bundlemcp.domain.bundles.presented_tool import PresentedTool


def merge_overrides(
    base: dict[str, Any] | None, override: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Shallow merge; explicit per-tool overrides win; a None value removes a key."""
    if override is None:
        return base
    merged = dict(base or {})
    for key, value in override.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged or None


class OverrideStage(BaseModel):
    """Applies the bundle's per-tool overrides: name, title, description and annotations.

    It runs after the profile, so an explicit annotation override wins over the
    profile's rewrite.
    """

    model_config = ConfigDict(frozen=True)

    def apply(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        if curation is None:
            return tool
        return tool.model_copy(
            update={
                "presented_name": PresentedName.for_tool(
                    tool.server.name, tool.tool.name, curation.override_name
                ),
                "title": curation.override_title or tool.title,
                "description": curation.override_description or tool.description,
                "annotations": merge_overrides(tool.annotations, curation.override_annotations),
            }
        )
