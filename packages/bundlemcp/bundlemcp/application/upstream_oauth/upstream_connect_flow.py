"""The interactive connect: send the user upstream, exchange the code they bring back."""

import uuid

from bundlemcp.application.contracts.upstream.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.application.upstream_oauth.authorize_start import AuthorizeStart
from bundlemcp.application.upstream_oauth.upstream_token_storage import UpstreamTokenStorage
from bundlemcp.domain.oauth.pkce import PkcePair
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.resource_indicator import canonical_resource
from bundlemcp.domain.upstream_oauth.upstream_client_config import UpstreamClientConfig
from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata

CLIENT_NAME = "bundlemcp"  # how the gateway names itself when it registers upstream


class UpstreamConnectFlow:
    """How the gateway identifies itself upstream, and how it gets its first token.

    The client identity follows the MCP authorization spec's order: a client
    an admin stored, else the gateway's client metadata document as its id,
    else dynamic registration. A client the gateway obtained itself is bound
    to the issuer it was obtained from and is replaced when that changes.
    """

    def __init__(
        self,
        tokens: UpstreamTokenStorage,
        provider: UpstreamOAuthProvider,
        *,
        metadata_document_url: str | None = None,
    ) -> None:
        # metadata_document_url is None when the gateway is not served over https,
        # where an authorization server cannot fetch its client metadata document
        self._tokens = tokens
        self._provider = provider
        self._metadata_document_url = metadata_document_url

    async def metadata(self, server: McpServer) -> UpstreamMetadata:
        """Configured or remembered endpoints win; otherwise discover them from the server."""
        config = await self._tokens.find_client_config(server.id)
        cached = config.metadata if config is not None else {}
        if cached.get("authorization_endpoint") and cached.get("token_endpoint"):
            meta = UpstreamMetadata(**cached)
        else:
            meta = await self._provider.discover(server.url)
        if not meta.resource:  # UPS-36: remembered before resources were recorded
            meta = meta.model_copy(update={"resource": canonical_resource(server.url)})
        return meta

    async def _requested_scope(
        self, server: McpServer, meta: UpstreamMetadata, config: UpstreamClientConfig
    ) -> str | None:
        """The scope to request, asking the protected resource when the metadata has none.

        Which scopes a resource needs is a fact about the resource, not about its
        authorization server, so remembered or admin-entered endpoints may lack
        it. The resource is asked again then; when it names none, or cannot be
        asked, only the scopes an upstream later demanded are requested, if any.
        """
        resource_scopes = meta.resource_scopes
        if not resource_scopes:
            try:
                resource_scopes = (await self._provider.discover(server.url)).resource_scopes
            except NeedsConnect:  # UPS-25
                resource_scopes = []
        return meta.model_copy(
            update={"resource_scopes": resource_scopes, "step_up_scopes": config.step_up_scopes}
        ).authorization_scope

    # UPS-37
    async def ensure_client(self, server: McpServer, redirect_uri: str) -> UpstreamClientConfig:
        """The client this gateway uses at the server's authorization server, obtaining one.

        An admin-stored client is used as it is. A client the gateway obtained
        earlier is reused while its issuer is still the server's; when the
        server moved to another authorization server it is discarded along with
        its tokens and a new one is obtained.
        """
        config = await self._tokens.find_client_config(server.id)
        if config is not None and config.is_admin_stored:
            return config
        meta = await self._provider.discover(server.url)
        if config is not None:
            if config.issuer is None or config.issuer == meta.issuer:
                return config
            await self._tokens.forget_registration(server.id)
        identification = meta.automatic_identification(
            metadata_document_usable=self._metadata_document_url is not None
        )
        if identification == ClientIdentification.METADATA_DOCUMENT:
            assert self._metadata_document_url is not None  # implied by the identification
            registration = UpstreamClientRegistration(client_id=self._metadata_document_url)
        elif identification == ClientIdentification.DYNAMIC_REGISTRATION:
            registration = await self._provider.register(
                meta, redirect_uri=redirect_uri, client_name=CLIENT_NAME
            )
        else:
            raise NeedsConnect(server.name, "no_client_config")
        return await self._tokens.save_registration(server.id, registration, meta, identification)

    async def begin(self, server: McpServer, redirect_uri: str, state: str) -> AuthorizeStart:
        # UPS-25/27: PKCE S256 connect
        pkce = PkcePair.generate()
        config = await self.ensure_client(server, redirect_uri)
        if config.grant == UpstreamGrant.CLIENT_CREDENTIALS:
            raise NeedsConnect(server.name, "client_credentials_client")
        meta = await self.metadata(server)
        if config.issuer is not None and meta.issuer is not None and config.issuer != meta.issuer:
            # UPS-37: an admin-stored client is never presented to another issuer
            raise NeedsConnect(server.name, "client_issuer_mismatch")
        url = self._provider.authorize_url(
            meta,
            client_id=config.client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=pkce.challenge,
            scope=await self._requested_scope(server, meta, config),
        )
        # UPS-32: record the issuer now, from validated metadata, never from the callback
        return AuthorizeStart(
            url=url,
            code_verifier=pkce.verifier,
            issuer=meta.issuer,
            iss_required=meta.authorization_response_iss_parameter_supported,
        )

    async def complete(
        self,
        server: McpServer,
        user_id: uuid.UUID | None,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> None:
        config = await self._tokens.client_config(server.id)
        meta = await self.metadata(server)
        tokens = await self._provider.exchange(
            meta,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            client_id=config.client_id,
            client_secret=config.client_secret,
        )
        await self._tokens.save(server.id, user_id, tokens)

    # UPS-35
    async def grant_client_credentials(self, server: McpServer) -> str:
        """Obtain and store the shared token of a client-credentials client."""
        config = await self._tokens.client_config(server.id)
        if config.grant != UpstreamGrant.CLIENT_CREDENTIALS or not config.client_secret:
            raise NeedsConnect(server.name, "not_client_credentials")
        meta = await self.metadata(server)
        tokens = await self._provider.client_credentials(
            meta,
            client_id=config.client_id,
            client_secret=config.client_secret,
            scope=await self._requested_scope(server, meta, config),
        )
        await self._tokens.save(server.id, None, tokens)
        return tokens.access_token
