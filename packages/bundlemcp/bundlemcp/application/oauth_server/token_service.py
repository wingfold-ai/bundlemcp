"""The token endpoint's business logic: client authentication, grants, revocation."""

from collections.abc import Sequence

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.oauth_server.authorization_code_grant import AuthorizationCodeGrant
from bundlemcp.application.oauth_server.client_authenticator import OAuthClientAuthenticator
from bundlemcp.application.oauth_server.refresh_token_grant import RefreshTokenGrant
from bundlemcp.application.oauth_server.token_grant import TokenGrant
from bundlemcp.application.oauth_server.token_issuer import TokenIssuer
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.client_credentials import ClientCredentials
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token


class OAuthTokenService:
    def __init__(self, uow: UnitOfWork, grants: Sequence[TokenGrant] | None = None) -> None:
        # grants defaults to the two this server supports; a caller may narrow the list
        self._uow = uow
        self._clients = OAuthClientAuthenticator(uow)
        self._client_rows = uow.oauth_clients
        self._tokens = uow.oauth_tokens
        if grants is None:
            issuer = TokenIssuer(uow)
            grants = (
                AuthorizationCodeGrant(uow, issuer),
                RefreshTokenGrant(uow, issuer),
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
        try:
            tokens = await grant.exchange(client, request)
        except OAuthError:
            # A refused grant may still have recorded something that must
            # outlive it: the client's last use, or a token family revoked
            # because its refresh token was replayed.
            await self._uow.commit()
            raise
        await self._uow.commit()
        return tokens

    async def revoke(self, credentials: ClientCredentials, token: str) -> None:
        """Revoke by access or refresh token on behalf of the client it was issued to.

        The client authenticates as it does at the token endpoint (RFC 7009
        section 2.1); a token that is unknown, or that belongs to another
        client, is ignored so the endpoint reveals nothing about it.
        """
        client = await self._clients.authenticate(credentials)
        if client is None:
            raise OAuthError("invalid_client", status=401)
        digest = hash_token(token)
        row = await self._tokens.by_either_hash(digest)
        if row is None or row.client_id != client.client_id:
            return
        row.revoked = True
        self._tokens.add(row)
        await self._uow.commit()
