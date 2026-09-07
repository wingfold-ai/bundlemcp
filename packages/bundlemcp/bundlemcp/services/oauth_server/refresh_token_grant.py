from bundlemcp.crypto import hash_token
from bundlemcp.models import OAuthAccessToken, OAuthClient
from bundlemcp.schemas import TokenResponse
from bundlemcp.services.errors import OAuthError
from bundlemcp.services.oauth_server.token_issuer import TokenIssuer
from bundlemcp.services.oauth_server.token_request import TokenRequest
from bundlemcp.store import Repository, UnitOfWork


class RefreshTokenGrant:
    """Rotate a refresh token: the old pair is revoked as the new one is issued.

    A refresh token presented again after it was rotated is the signature of
    a stolen token, so the whole family descended from the original grant is
    revoked, whichever party still holds the newest one.
    """

    grant_type = "refresh_token"

    def __init__(self, uow: UnitOfWork, issuer: TokenIssuer) -> None:
        self._tokens = Repository(uow.session, OAuthAccessToken)
        self._issuer = issuer

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        if not request.refresh_token:
            raise OAuthError("invalid_request", "refresh_token required")
        current = await self._tokens.one(
            OAuthAccessToken.refresh_token_hash == hash_token(request.refresh_token)
        )
        if current is None or current.client_id != client.client_id:
            raise OAuthError("invalid_grant")
        if current.revoked:
            await self._revoke_family(current)  # RFC 9700 section 4.14.2
            raise OAuthError("invalid_grant")
        if not current.is_refreshable:
            raise OAuthError("invalid_grant")
        # OAS-4 rotation as a compare-and-set: a concurrent rotation of the same
        # token is a replay too, and it is refused the same way.
        rotated = await self._tokens.update_where(
            OAuthAccessToken.id == current.id,
            OAuthAccessToken.revoked.is_(False),  # type: ignore[union-attr]
            revoked=True,
        )
        if rotated != 1:
            await self._revoke_family(current)
            raise OAuthError("invalid_grant")
        return self._issuer.issue(
            client_id=client.client_id,
            user_id=current.user_id,
            endpoint_id=current.endpoint_id,
            scope=current.scope,
            family_id=current.family_id,
        )

    async def _revoke_family(self, member: OAuthAccessToken) -> None:
        await self._tokens.update_where(
            OAuthAccessToken.family_id == member.family_id, revoked=True
        )
