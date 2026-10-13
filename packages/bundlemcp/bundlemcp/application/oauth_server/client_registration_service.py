"""Dynamic client registration (RFC 7591)."""

from collections.abc import Iterable

from bundlemcp.application.contracts.live_state.rate_limiter import RateLimiter
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.schemas import ClientRegistrationRequest, ClientRegistrationResponse
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.oauth.redirect_uri_rule import InvalidRedirectUri, check_redirect_uri
from bundlemcp.domain.oauth.registration_policy import RegistrationPolicy
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher

REGISTRATION_RATE_SCOPE = "dcr:{ip}"  # per-IP registration counter


class ClientRegistrationService:
    """Registers OAuth clients, checking the cheapest refusals first.

    The redirect URIs are checked in memory, the per-IP budget in the shared
    rate-limit store, and only then is the database asked how many
    registrations are still unused, so a flood of refusable requests never
    reaches it.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        public_base: str,
        generator: SecretGenerator,
        hasher: SecretHasher,
        policy: RegistrationPolicy,
        rate_limiter: RateLimiter,
    ) -> None:
        self._uow = uow
        self._public_base = public_base
        self._generator = generator
        self._hasher = hasher
        self._policy = policy
        self._rate_limiter = rate_limiter
        self._clients = uow.oauth_clients

    async def register(
        self, request: ClientRegistrationRequest, client_ip: str
    ) -> ClientRegistrationResponse:
        """Register a client for a request arriving from this IP, or refuse it.

        Raises OAuthError: ``invalid_redirect_uri`` for a URI the gateway does
        not accept, ``too_many_requests`` when the IP's budget or the global
        quota of unused registrations is spent.
        """
        self._check_redirect_uris(request.redirect_uris)
        if self._policy.limits_per_ip(request.redirect_uris):
            rate = await self._rate_limiter.check(
                REGISTRATION_RATE_SCOPE.format(ip=client_ip),
                self._policy.per_ip_limit,
                self._policy.per_ip_window,
            )
            if not rate.allowed:
                raise OAuthError(
                    OAuthErrorCode.TOO_MANY_REQUESTS, "registration rate limit exceeded"
                )
        if not self._policy.admits_another(await self._clients.count_never_used()):
            raise OAuthError(
                OAuthErrorCode.TOO_MANY_REQUESTS,
                "too many registered clients have not been used yet; try again later",
            )
        client_id = f"bmcp_client_{self._generator.token(16)}"
        client_secret: str | None = None
        if request.token_endpoint_auth_method != TokenEndpointAuthMethod.NONE:
            client_secret = self._generator.token(32)
        self._clients.add(
            OAuthClient(
                client_id=client_id,
                client_secret_hash=self._hasher.digest(client_secret) if client_secret else None,
                client_name=request.client_name,
                redirect_uris=request.redirect_uris,
                grant_types=request.grant_types,
                token_endpoint_auth_method=request.token_endpoint_auth_method,
                scope=request.scope,
                application_type=request.application_type,
            )
        )
        await self._uow.commit()
        return ClientRegistrationResponse(
            client_id=client_id,
            client_secret=client_secret,  # shown once
            client_name=request.client_name,
            redirect_uris=request.redirect_uris,
            grant_types=request.grant_types,
            response_types=request.response_types,
            token_endpoint_auth_method=request.token_endpoint_auth_method,
            scope=request.scope,
            application_type=request.application_type,
            authorization_endpoint=f"{self._public_base}/oauth/authorize",
            token_endpoint=f"{self._public_base}/oauth/token",
        )

    def _check_redirect_uris(self, uris: Iterable[str]) -> None:
        for uri in uris:
            # RFC 7591 section 3.2.2: the protocol's error code, not a generic 4xx
            try:
                check_redirect_uri(uri)
            except InvalidRedirectUri:
                raise OAuthError(
                    OAuthErrorCode.INVALID_REDIRECT_URI,
                    f"{uri} must be https, or http on localhost",
                ) from None
            if not self._policy.allowed_redirect_uris.permits(uri):
                raise OAuthError(
                    OAuthErrorCode.INVALID_REDIRECT_URI,
                    f"{uri} is not a redirect URI this gateway accepts",
                )
