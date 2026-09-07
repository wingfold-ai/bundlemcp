"""Deciding who a caller is, trying each credential kind the endpoint accepts."""

from collections.abc import Sequence

from fastapi import Request

from bundlemcp.gateway.composition import BundleView
from bundlemcp.gateway.mcp_endpoint.authentication.anonymous_authenticator import (
    AnonymousAuthenticator,
)
from bundlemcp.gateway.mcp_endpoint.authentication.api_key_authenticator import (
    ApiKeyAuthenticator,
)
from bundlemcp.gateway.mcp_endpoint.authentication.credential_authenticator import (
    CredentialAuthenticator,
)
from bundlemcp.gateway.mcp_endpoint.authentication.oauth_bearer_authenticator import (
    OAuthBearerAuthenticator,
)
from bundlemcp.models import CallerIdentity
from bundlemcp.services import AuthService
from bundlemcp.store import UnitOfWork

# Strongest credential first: a valid token wins over a key, and only an
# endpoint that accepts nobody falls through to anonymous.
DEFAULT_PRECEDENCE: tuple[CredentialAuthenticator, ...] = (
    OAuthBearerAuthenticator(),
    ApiKeyAuthenticator(),
    AnonymousAuthenticator(),
)


class EndpointAuthentication:
    def __init__(
        self, authenticators: Sequence[CredentialAuthenticator] = DEFAULT_PRECEDENCE
    ) -> None:
        self._authenticators = tuple(authenticators)

    async def authenticate(
        self, request: Request, uow: UnitOfWork, view: BundleView
    ) -> CallerIdentity | None:
        """The first identity an accepted authenticator can vouch for, else None."""
        auth = AuthService(uow)
        for authenticator in self._authenticators:
            if not view.endpoint.accepts(authenticator.mode):
                continue
            identity = await authenticator.authenticate(request, view, auth)
            if identity is not None:
                return identity
        return None
