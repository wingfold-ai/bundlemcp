"""Deciding who a caller is, trying each credential kind the endpoint accepts."""

from collections.abc import Sequence

from fastapi import Request

from bundlemcp.api.mcp.routing.authentication.anonymous_authenticator import (
    AnonymousAuthenticator,
)
from bundlemcp.api.mcp.routing.authentication.api_key_authenticator import (
    ApiKeyAuthenticator,
)
from bundlemcp.api.mcp.routing.authentication.credential_authenticator import (
    CredentialAuthenticator,
)
from bundlemcp.api.mcp.routing.authentication.oauth_bearer_authenticator import (
    OAuthBearerAuthenticator,
)
from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.bundles.bundle_view import BundleView
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher

# Strongest credential first: a valid token wins over a key, and only an
# endpoint that accepts nobody falls through to anonymous.
DEFAULT_PRECEDENCE: tuple[CredentialAuthenticator, ...] = (
    OAuthBearerAuthenticator(),
    ApiKeyAuthenticator(),
    AnonymousAuthenticator(),
)


class EndpointAuthentication:
    """Runs the endpoint's accepted credential kinds against one request.

    The clock and the hasher are the two primitives the authenticators need and
    cannot get from the request: an API key or access token is looked up by
    ``hasher`` digest — the gateway stores digests, never the secret — and
    ``clock`` is the instant its expiry and its last-used window are judged
    against. Both arrive from the composition root so a test can pin either.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        hasher: SecretHasher,
        authenticators: Sequence[CredentialAuthenticator] = DEFAULT_PRECEDENCE,
    ) -> None:
        self._clock = clock
        self._hasher = hasher
        self._authenticators = tuple(authenticators)

    async def authenticate(
        self, request: Request, uow: UnitOfWork, view: BundleView
    ) -> CallerIdentity | None:
        """The first identity an accepted authenticator can vouch for, else None."""
        auth = AuthService(uow, clock=self._clock, hasher=self._hasher)
        for authenticator in self._authenticators:
            if not view.endpoint.accepts(authenticator.mode):
                continue
            identity = await authenticator.authenticate(request, view, auth)
            if identity is not None:
                return identity
        return None
