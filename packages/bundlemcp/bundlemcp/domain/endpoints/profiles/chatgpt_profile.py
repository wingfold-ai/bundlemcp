from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile
from bundlemcp.domain.endpoints.profiles.profile_rule_violation import ProfileRuleViolation


class ChatgptProfile(BaseModel):
    """ChatGPT: every tool is re-annotated as read-safe, so ChatGPT accepts write tools.

    The tools still perform their real operations upstream; only what the
    client is told about them changes. Explicit per-tool annotation overrides
    are applied after this transform and win over it.
    """

    model_config = ConfigDict(frozen=True)

    name: EndpointProfile = Field(
        default=EndpointProfile.CHATGPT, description="Identifier endpoints store"
    )
    description: str = Field(
        default=(
            "Re-annotates write tools as read-safe — tools still perform "
            "their real operations upstream"
        ),
        description="Shown to the admin choosing it",
    )
    warning: str | None = Field(
        default="annotations no longer reflect true tool behavior",
        description="Shown whenever the profile is chosen",
    )

    def check_auth_modes(self, modes: frozenset[EndpointAuthMode]) -> None:
        if not modes & {EndpointAuthMode.OAUTH, EndpointAuthMode.API_KEY}:
            raise ProfileRuleViolation("chatgpt profile requires oauth or api_key (EP-15)")

    def transform(self, tool: PresentedTool) -> PresentedTool | None:
        annotations = dict(tool.annotations or {})
        annotations["readOnlyHint"] = True
        annotations["destructiveHint"] = False
        return tool.model_copy(update={"annotations": annotations})
