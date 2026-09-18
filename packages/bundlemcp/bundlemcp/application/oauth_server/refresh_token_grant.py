from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.oauth_server.token_issuer import TokenIssuer
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class RefreshTokenGrant:
    """Rotate a refresh token: the old pair is revoked as the new one is issued.

    A refresh token presented again after it was rotated is the signature of
    a stolen token, so the whole family descended from the original grant is
    revoked, whichever party still holds the newest one.
    """

    grant_type = GrantType.REFRESH_TOKEN

    def __init__(
        self, uow: UnitOfWork, issuer: TokenIssuer, clock: Clock, hasher: SecretHasher
    ) -> None:
        self._tokens = uow.oauth_tokens
        self._issuer = issuer
        self._clock = clock
        self._hasher = hasher

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        if not request.refresh_token:
            raise OAuthError(OAuthErrorCode.INVALID_REQUEST, "refresh_token required")
        current = await self._tokens.by_refresh_hash(self._hasher.digest(request.refresh_token))
        if current is None or current.client_id != client.client_id:
            raise OAuthError(OAuthErrorCode.INVALID_GRANT)
        if current.revoked:
            await self._revoke_family(current)  # RFC 9700 section 4.14.2
            raise OAuthError(OAuthErrorCode.INVALID_GRANT)
        if not current.is_refreshable_at(self._clock.now()):
            raise OAuthError(OAuthErrorCode.INVALID_GRANT)
        # OAS-4 rotation as a compare-and-set: a concurrent rotation of the same
        # token is a replay too, and it is refused the same way.
        if not await self._tokens.revoke_unless_revoked(current.id):
            await self._revoke_family(current)
            raise OAuthError(OAuthErrorCode.INVALID_GRANT)
        return self._issuer.issue(
            client_id=client.client_id,
            user_id=current.user_id,
            endpoint_id=current.endpoint_id,
            scope=current.scope,
            family_id=current.family_id,
        )

    async def _revoke_family(self, member: OAuthAccessToken) -> None:
        await self._tokens.revoke_family(member.family_id)
