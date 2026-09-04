from typing import Protocol, runtime_checkable

from bundlemcp.models import OAuthClient
from bundlemcp.schemas import TokenResponse
from bundlemcp.services.oauth_server.token_request import TokenRequest


@runtime_checkable
class TokenGrant(Protocol):
    """One way a client may obtain tokens at the token endpoint."""

    @property
    def grant_type(self) -> str:
        """The grant_type value this grant serves."""
        ...

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        """Validate the request for this grant and stage a new token pair.

        Raises OAuthError with the protocol's error code when the request fails.
        """
        ...
