from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles.profile_rule_violation import ProfileRuleViolation


class ClaudeProfile(BaseModel):
    """claude.ai's remote connector: OAuth only, tools passed through unchanged."""

    model_config = ConfigDict(frozen=True)

    name: EndpointProfile = Field(
        default=EndpointProfile.CLAUDE, description="Identifier endpoints store"
    )
    description: str = Field(
        default="claude.ai remote connector: OAuth-only, passthrough tools",
        description="Shown to the admin choosing it",
    )
    warning: str | None = Field(default=None, description="No caution for this profile")

    def check_auth_modes(self, modes: frozenset[EndpointAuthMode]) -> None:
        if modes != {EndpointAuthMode.OAUTH}:
            raise ProfileRuleViolation("claude profile requires auth_modes == ['oauth'] (EP-15)")

    def transform(self, tool: PresentedTool) -> PresentedTool | None:
        return tool
