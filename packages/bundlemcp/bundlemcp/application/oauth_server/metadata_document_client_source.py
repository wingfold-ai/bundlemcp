from bundlemcp.application.contracts.identity.client_metadata_fetcher import ClientMetadataFetcher
from bundlemcp.application.contracts.persistence.oauth_client_repository import (
    OAuthClientRepository,
)
from bundlemcp.application.errors import InvalidInputError
from bundlemcp.application.oauth_server.registered_client_source import METADATA_DOCUMENT_SCHEME
from bundlemcp.domain.oauth.client_id_metadata_document import InvalidClientMetadataDocument
from bundlemcp.domain.oauth.oauth_client import OAuthClient
from bundlemcp.domain.oauth.redirect_uri_allow_list import RedirectUriAllowList
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod


class MetadataDocumentClientSource:
    """Clients that publish a metadata document at the https URL they use as client_id.

    Such a client needs no registration: its document is fetched, checked, and
    mirrored into the client table so codes, tokens and consent bind to it like
    any other client. The mirror is refreshed on every resolution, so a changed
    document takes effect at once. It is only staged here; the caller commits
    when the client is actually used, so a look-up on its own writes nothing.
    """

    def __init__(
        self,
        clients: OAuthClientRepository,
        fetcher: ClientMetadataFetcher,
        *,
        allowed_redirect_uris: RedirectUriAllowList,
    ) -> None:
        self._clients = clients
        self._fetcher = fetcher
        self._allowed_redirect_uris = allowed_redirect_uris

    def handles(self, client_id: str) -> bool:
        return client_id.startswith(METADATA_DOCUMENT_SCHEME)

    async def resolve(self, client_id: str) -> OAuthClient | None:
        # OAS-13
        document = await self._fetcher.fetch(client_id)
        try:
            document.check(fetched_from=client_id, allowed=self._allowed_redirect_uris)
        except InvalidClientMetadataDocument as exc:
            raise InvalidInputError(str(exc)) from None
        client = await self._clients.get(client_id)
        if client is None:
            client = OAuthClient(
                client_id=client_id, token_endpoint_auth_method=TokenEndpointAuthMethod.NONE
            )
        client.apply_metadata_document(document)
        self._clients.add(client)
        return client
