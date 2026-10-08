"""The limits dynamic client registration runs under."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.oauth.redirect_uri_allow_list import RedirectUriAllowList


class RegistrationPolicy(BaseModel):
    """Which registrations are accepted, and how many may arrive.

    Three limits hold together. Redirect URIs must be on the operator's
    allow-list when one is configured. Each client IP gets a fixed number of
    registrations per window, unless every redirect URI it registers is one
    the operator listed: a trusted client such as claude.ai registers from its
    own servers, so all its users would otherwise share one IP's budget. And
    however a registration got past the per-IP limit, the number of
    registrations that have not yet obtained a token is capped globally.
    """

    model_config = ConfigDict(frozen=True)

    allowed_redirect_uris: RedirectUriAllowList = Field(
        default_factory=RedirectUriAllowList,
        description="Redirect URIs clients may register or declare; empty leaves all open",
    )
    per_ip_limit: int = Field(ge=1, description="Registrations one client IP may make per window")
    per_ip_window: int = Field(ge=1, description="Length in seconds of the per-IP window")
    max_unused_clients: int = Field(
        ge=1,
        description="Maximum number of registered clients that never obtained a token; at "
        "this count further registrations are refused",
    )

    def limits_per_ip(self, redirect_uris: Iterable[str]) -> bool:
        """Whether a registration for these redirect URIs counts against its IP's budget."""
        return not self.allowed_redirect_uris.vouches_for(redirect_uris)

    def admits_another(self, unused_clients: int) -> bool:
        """Whether one more registration fits beside this many never-used clients."""
        return unused_clients < self.max_unused_clients
