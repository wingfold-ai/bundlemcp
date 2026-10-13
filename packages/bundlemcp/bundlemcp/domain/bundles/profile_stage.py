from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.bundle_tool import BundleTool
from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.profiles.endpoint_profile_preset import EndpointProfilePreset


class ProfileStage(BaseModel):
    """Applies the endpoint profile's transform; the profile may also hide a tool."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    preset: EndpointProfilePreset = Field(description="The profile of the endpoint being served")

    def apply(self, tool: PresentedTool, curation: BundleTool | None) -> PresentedTool | None:
        return self.preset.transform(tool)
