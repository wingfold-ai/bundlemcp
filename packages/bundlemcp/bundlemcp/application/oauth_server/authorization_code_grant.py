from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.oauth_server.requested_resource import ensure_resource_is_the_audience
from bundlemcp.application.oauth_server.token_issuer import TokenIssuer
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class AuthorizationCodeGrant:
    """Redeem a single-use authorization code, proving possession with PKCE."""

    grant_type = GrantType.AUTHORIZATION_CODE

    def __init__(
        self, uow: UnitOfWork, issuer: TokenIssuer, clock: Clock, hasher: SecretHasher
    ) -> None:
        self._uow = uow
        self._codes = uow.authorization_codes
        self._issuer = issuer
        self._clock = clock
        self._hasher = hasher

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        if not request.code or not request.code_verifier:
            raise OAuthError(OAuthErrorCode.INVALID_REQUEST, "code and code_verifier required")
        code = await self._codes.get(self._hasher.digest(request.code))
        if (
            code is None
            or not code.is_redeemable_at(self._clock.now())
            or not code.issued_to(client.client_id)
        ):
            raise OAuthError(OAuthErrorCode.INVALID_GRANT)
        if not code.sent_to(request.redirect_uri):
            raise OAuthError(OAuthErrorCode.INVALID_GRANT, "redirect_uri mismatch")
        if not code.proves_possession(request.code_verifier):
            raise OAuthError(OAuthErrorCode.INVALID_GRANT, "PKCE verification failed")
        await ensure_resource_is_the_audience(self._uow, request, code.endpoint_id)
        # the burn is a compare-and-set, so two concurrent redemptions
        # that both read an unused code cannot both be issued a pair.
        if not await self._codes.burn(code.code_hash):
            raise OAuthError(OAuthErrorCode.INVALID_GRANT)
        return self._issuer.issue(
            client_id=client.client_id,
            user_id=code.user_id,
            endpoint_id=code.endpoint_id,
            scope=code.scope,
        )
