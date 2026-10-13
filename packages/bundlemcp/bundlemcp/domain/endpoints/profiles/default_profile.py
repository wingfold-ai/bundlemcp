from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile


class DefaultProfile(BaseModel):
    """Passthrough: any authentication mode, tools exactly as curated."""

    model_config = ConfigDict(frozen=True)

    name: EndpointProfile = Field(
        default=EndpointProfile.DEFAULT, description="Identifier endpoints store"
    )
    description: str = Field(
        default="Passthrough; any auth mode", description="Shown to the admin choosing it"
    )
    warning: str | None = Field(default=None, description="No caution for this profile")

    def check_auth_modes(self, modes: frozenset[EndpointAuthMode]) -> None:
        return None

    def transform(self, tool: PresentedTool) -> PresentedTool | None:
        return tool
