from sqlalchemy.ext.asyncio import AsyncSession

from bundlemcp.crypto import hash_token, tokens_equal
from bundlemcp.models import OAuthClient
from bundlemcp.services.oauth_server.client_credentials import ClientCredentials
from bundlemcp.store import Repository


class OAuthClientAuthenticator:
    """Public clients prove nothing here (PKCE does); confidential ones present a secret."""

    def __init__(self, session: AsyncSession) -> None:
        self._clients = Repository(session, OAuthClient)

    async def authenticate(self, credentials: ClientCredentials) -> OAuthClient | None:
        client = await self._clients.get(credentials.client_id)
        if client is None:
            return None
        if client.token_endpoint_auth_method == "none":
            return client
        if not credentials.client_secret or client.client_secret_hash is None:
            return None
        if not tokens_equal(hash_token(credentials.client_secret), client.client_secret_hash):
            return None
        return client
