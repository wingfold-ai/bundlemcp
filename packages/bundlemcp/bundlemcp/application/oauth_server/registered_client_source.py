from bundlemcp.application.contracts.persistence.oauth_client_repository import (
    OAuthClientRepository,
)
from bundlemcp.domain.oauth.oauth_client import OAuthClient

METADATA_DOCUMENT_SCHEME = "https://"  # AUTH-13: a URL-shaped client_id is a metadata document


class RegisteredClientSource:
    """Clients that registered with this gateway (RFC 7591) and were given an opaque id."""

    def __init__(self, clients: OAuthClientRepository) -> None:
        self._clients = clients

    def handles(self, client_id: str) -> bool:
        return not client_id.startswith(METADATA_DOCUMENT_SCHEME)

    async def resolve(self, client_id: str) -> OAuthClient | None:
        return await self._clients.get(client_id)
