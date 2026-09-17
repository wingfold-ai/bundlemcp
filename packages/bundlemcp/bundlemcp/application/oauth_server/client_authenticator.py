from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.oauth.client_credentials import ClientCredentials
from bundlemcp.domain.oauth.oauth_client import OAuthClient


class OAuthClientAuthenticator:
    """Public clients prove nothing here (PKCE does); confidential ones present a secret."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._clients = uow.oauth_clients

    async def authenticate(self, credentials: ClientCredentials) -> OAuthClient | None:
        client = await self._clients.get(credentials.client_id)
        if client is None:
            return None
        if client.is_public:
            return client
        return client if client.verifies_secret(credentials.client_secret) else None
