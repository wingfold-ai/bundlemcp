"""Turning a client_id into a client, whichever way the client identifies itself."""

from collections.abc import Sequence

from bundlemcp.application.oauth_server.client_source import ClientSource
from bundlemcp.domain.oauth.oauth_client import OAuthClient


class ClientResolver:
    """Asks each source in turn; the first that handles the identifier answers."""

    def __init__(self, sources: Sequence[ClientSource]) -> None:
        self._sources = tuple(sources)

    async def resolve(self, client_id: str) -> OAuthClient | None:
        """The client behind an identifier, or None when no source knows it."""
        for source in self._sources:
            if source.handles(client_id):
                return await source.resolve(client_id)
        return None
