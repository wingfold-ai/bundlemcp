from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.crypto import hash_token, pkce_verifies
from bundlemcp.models import OAuthAuthorizationCode, OAuthClient
from bundlemcp.schemas import TokenResponse
from bundlemcp.services.errors import OAuthError
from bundlemcp.services.oauth_server.token_issuer import TokenIssuer
from bundlemcp.services.oauth_server.token_request import TokenRequest
from bundlemcp.store import Repository


class AuthorizationCodeGrant:
    """Redeem a single-use authorization code, proving possession with PKCE."""

    grant_type = "authorization_code"

    def __init__(self, session: AsyncSession, issuer: TokenIssuer) -> None:
        self._codes = Repository(session, OAuthAuthorizationCode)
        self._issuer = issuer

    async def exchange(self, client: OAuthClient, request: TokenRequest) -> TokenResponse:
        if not request.code or not request.code_verifier:
            raise OAuthError("invalid_request", "code and code_verifier required")
        code = await self._codes.get(hash_token(request.code))
        if code is None or not code.is_redeemable or code.client_id != client.client_id:
            raise OAuthError("invalid_grant")
        if request.redirect_uri != code.redirect_uri:
            raise OAuthError("invalid_grant", "redirect_uri mismatch")
        if not pkce_verifies(request.code_verifier, code.code_challenge):
            raise OAuthError("invalid_grant", "PKCE verification failed")
        # OAS-3: the burn is a compare-and-set, so two concurrent redemptions
        # that both read an unused code cannot both be issued a pair.
        burned = await self._codes.update_where(
            OAuthAuthorizationCode.code_hash == code.code_hash,
            OAuthAuthorizationCode.used.is_(False),  # type: ignore[union-attr]
            used=True,
        )
        if burned != 1:
            raise OAuthError("invalid_grant")
        return self._issuer.issue(
            client_id=client.client_id,
            user_id=code.user_id,
            endpoint_id=code.endpoint_id,
            scope=code.scope,
        )
