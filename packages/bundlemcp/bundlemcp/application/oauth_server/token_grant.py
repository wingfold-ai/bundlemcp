from typing import Protocol, runtime_checkable

from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_client import OAuthClient


@runtime_checkable
class TokenGrant(Protocol):
    """One way a client may obtain tokens at the token endpoint."""

    @property
    def grant_type(self) -> GrantType:
        """The grant_type value this grant serves."""
        ...

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        """Validate the request for this grant and stage a new token pair.

        Raises OAuthError with the protocol's error code when the request fails.
        """
        ...
