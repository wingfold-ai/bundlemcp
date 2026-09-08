from typing import Protocol, runtime_checkable

from bundlemcp.domain.oauth.client_id_metadata_document import (
    ClientIdMetadataDocument,
)


@runtime_checkable
class ClientMetadataFetcher(Protocol):
    """Resolves a URL-shaped client_id to the metadata document published there."""

    async def fetch(self, client_id_url: str) -> ClientIdMetadataDocument:
        """The document, or InvalidInputError when it cannot be fetched or is malformed."""
        ...
