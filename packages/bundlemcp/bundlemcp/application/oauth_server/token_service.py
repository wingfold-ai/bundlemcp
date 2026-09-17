"""The token endpoint's business logic: client authentication, grants, revocation."""

from collections.abc import Sequence

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import OAuthError
from bundlemcp.application.oauth_server.client_authenticator import OAuthClientAuthenticator
from bundlemcp.application.oauth_server.token_grant import TokenGrant
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.client_credentials import ClientCredentials
from bundlemcp.domain.oauth.oauth_error_code import OAuthErrorCode
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token


class OAuthTokenService:
    def __init__(
        self, uow: UnitOfWork, *, clients: OAuthClientAuthenticator, grants: Sequence[TokenGrant]
    ) -> None:
        # Which grants exist is the composition root's decision, not this service's.
        self._uow = uow
        self._clients = clients
        self._client_rows = uow.oauth_clients
        self._tokens = uow.oauth_tokens
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
            raise OAuthError(OAuthErrorCode.INVALID_CLIENT)
        client.last_used_at = utcnow()  # SEC-8 stale-client purge signal
        self._client_rows.add(client)
        grant = self._grants.get(request.grant_type)
        if grant is None:
            await self._uow.commit()
            raise OAuthError(OAuthErrorCode.UNSUPPORTED_GRANT_TYPE)
        if not client.allows_grant(grant.grant_type):
            # RFC 6749 section 5.2: the client exists but did not register for this grant
            await self._uow.commit()
            raise OAuthError(OAuthErrorCode.UNAUTHORIZED_CLIENT)
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
            raise OAuthError(OAuthErrorCode.INVALID_CLIENT)
        digest = hash_token(token)
        row = await self._tokens.by_either_hash(digest)
        if row is None or row.client_id != client.client_id:
            return
        row.revoked = True
        self._tokens.add(row)
        await self._uow.commit()
