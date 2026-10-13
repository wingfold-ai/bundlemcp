from typing import Protocol, runtime_checkable

from bundlemcp.domain.bundles.presented_tool import PresentedTool
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile


@runtime_checkable
class EndpointProfilePreset(Protocol):
    """Everything one endpoint profile decides, in one place.

    A profile is registered once, in the profile catalogue; the endpoint write
    validation, the management API's profile listing and the tool pipeline all
    ask it rather than branching on its name.
    """

    @property
    def name(self) -> EndpointProfile:
        """The stored identifier endpoints refer to."""
        ...

    @property
    def description(self) -> str:
        """What the profile does, for the admin choosing it."""
        ...

    @property
    def warning(self) -> str | None:
        """A caution the UI shows when the profile is chosen, or None."""
        ...

    def check_auth_modes(self, modes: frozenset[EndpointAuthMode]) -> None:
        """Raise ``ProfileRuleViolation`` when an endpoint may not use these modes with it."""
        ...

    def transform(self, tool: PresentedTool) -> PresentedTool | None:
        """The tool as this profile presents it, or None to hide it from the endpoint."""
        ...
