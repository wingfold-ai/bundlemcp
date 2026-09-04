from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.crypto import hash_token
from bundlemcp.models import OAuthAccessToken, OAuthClient
from bundlemcp.schemas import TokenResponse
from bundlemcp.services.errors import OAuthError
from bundlemcp.services.oauth_server.token_issuer import TokenIssuer
from bundlemcp.services.oauth_server.token_request import TokenRequest
from bundlemcp.store import Repository


class RefreshTokenGrant:
    """Rotate a refresh token: the old pair is revoked as the new one is issued."""

    grant_type = "refresh_token"

    def __init__(self, session: AsyncSession, issuer: TokenIssuer) -> None:
        self._tokens = Repository(session, OAuthAccessToken)
        self._issuer = issuer

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        if not request.refresh_token:
            raise OAuthError("invalid_request", "refresh_token required")
        current = await self._tokens.one(
            OAuthAccessToken.refresh_token_hash == hash_token(request.refresh_token)
        )
        if current is None or not current.is_refreshable or current.client_id != client.client_id:
            raise OAuthError("invalid_grant")
        current.revoked = True  # rotation (OAS-4)
        self._tokens.add(current)
        return self._issuer.issue(
            client_id=client.client_id,
            user_id=current.user_id,
            endpoint_id=current.endpoint_id,
            scope=current.scope,
        )
