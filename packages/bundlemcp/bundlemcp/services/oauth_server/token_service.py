"""The token endpoint's business logic: client authentication, grants, revocation."""

from collections.abc import Sequence

from bundlemcp.crypto import hash_token
from bundlemcp.models import OAuthAccessToken, OAuthClient, utcnow
from bundlemcp.schemas import TokenResponse
from bundlemcp.services.errors import OAuthError
from bundlemcp.services.oauth_server.authorization_code_grant import AuthorizationCodeGrant
from bundlemcp.services.oauth_server.client_authenticator import OAuthClientAuthenticator
from bundlemcp.services.oauth_server.client_credentials import ClientCredentials
from bundlemcp.services.oauth_server.refresh_token_grant import RefreshTokenGrant
from bundlemcp.services.oauth_server.token_grant import TokenGrant
from bundlemcp.services.oauth_server.token_issuer import TokenIssuer
from bundlemcp.services.oauth_server.token_request import TokenRequest
from bundlemcp.store import Repository, UnitOfWork


class OAuthTokenService:
    def __init__(self, uow: UnitOfWork, grants: Sequence[TokenGrant] | None = None) -> None:
        # grants defaults to the two this server supports; a caller may narrow the list
        self._uow = uow
        self._clients = OAuthClientAuthenticator(uow.session)
        self._client_rows = Repository(uow.session, OAuthClient)
        self._tokens = Repository(uow.session, OAuthAccessToken)
        if grants is None:
            issuer = TokenIssuer(uow.session)
            grants = (
                AuthorizationCodeGrant(uow.session, issuer),
                RefreshTokenGrant(uow.session, issuer),
            )
        self._grants = {grant.grant_type: grant for grant in grants}

    async def exchange(
        self, credentials: ClientCredentials, request: TokenRequest
    ) -> TokenResponse:
        """Authenticate the client and run the requested grant.

        Raises OAuthError; invalid_client and invalid_grant are the caller's cue
        to count an authentication failure.
        """
        client = await self._clients.authenticate(credentials)
        if client is None:
            raise OAuthError("invalid_client", status=401)
        client.last_used_at = utcnow()  # SEC-8 stale-client purge signal
        self._client_rows.add(client)
        grant = self._grants.get(request.grant_type)
        if grant is None:
            await self._uow.commit()
            raise OAuthError("unsupported_grant_type")
        tokens = await grant.exchange(client, request)
        await self._uow.commit()
        return tokens

    async def revoke(self, token: str) -> None:
        """Revoke by access or refresh token; unknown tokens are ignored (RFC 7009)."""
        digest = hash_token(token)
        row = await self._tokens.one(
            (OAuthAccessToken.access_token_hash == digest)
            | (OAuthAccessToken.refresh_token_hash == digest)
        )
        if row is None:
            return
        row.revoked = True
        self._tokens.add(row)
        await self._uow.commit()
