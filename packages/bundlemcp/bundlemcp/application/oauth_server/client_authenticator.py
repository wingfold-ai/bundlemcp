from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.oauth.client_credentials import ClientCredentials
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.shared.secrets import hash_token, tokens_equal


class OAuthClientAuthenticator:
    """Public clients prove nothing here (PKCE does); confidential ones present a secret."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._clients = uow.oauth_clients

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
