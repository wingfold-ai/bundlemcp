from collections.abc import Callable
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.oauth_server.token_issuer import TokenIssuer
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher


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


# Builds a grant for one request's transaction. The composition root lists
# which grants the token endpoint serves; a provider instantiates them.
TokenGrantFactory = Callable[[UnitOfWork, TokenIssuer, Clock, SecretHasher], TokenGrant]
