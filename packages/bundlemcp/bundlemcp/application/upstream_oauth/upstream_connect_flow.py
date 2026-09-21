"""The interactive connect: send the user upstream, exchange the code they bring back."""

import uuid

from bundlemcp.application.contracts.upstream.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.application.upstream_oauth.authorize_start import AuthorizeStart
from bundlemcp.application.upstream_oauth.upstream_token_storage import UpstreamTokenStorage
from bundlemcp.domain.oauth.pkce import PkcePair
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata

CLIENT_NAME = "bundlemcp"  # how the gateway names itself when it registers upstream


class UpstreamConnectFlow:
    def __init__(self, tokens: UpstreamTokenStorage, provider: UpstreamOAuthProvider) -> None:
        self._tokens = tokens
        self._provider = provider

    async def metadata(self, server: McpServer) -> UpstreamMetadata:
        """Configured or remembered endpoints win; otherwise discover them from the server."""
        config = await self._tokens.find_client_config(server.id)
        cached = config.metadata if config is not None else {}
        if cached.get("authorization_endpoint") and cached.get("token_endpoint"):
            return UpstreamMetadata(**cached)
        return await self._provider.discover(server.url)

    async def ensure_client(self, server: McpServer, redirect_uri: str) -> None:
        """Make sure the gateway has a client at the server's authorization server.

        A client an admin stored is used as it is. Without one, the gateway
        registers itself when the authorization server offers dynamic client
        registration; otherwise the admin has to store one.
        """
        if await self._tokens.find_client_config(server.id) is not None:
            return
        meta = await self._provider.discover(server.url)
        if not meta.registration_endpoint:
            raise NeedsConnect(server.name, "no_client_config")
        # UPO-1: dynamic registration, remembered with the metadata it was made against
        registration = await self._provider.register(
            meta, redirect_uri=redirect_uri, client_name=CLIENT_NAME
        )
        await self._tokens.save_registration(server.id, registration, meta)

    async def begin(self, server: McpServer, redirect_uri: str, state: str) -> AuthorizeStart:
        # UPO-1/3: PKCE S256 connect
        pkce = PkcePair.generate()
        await self.ensure_client(server, redirect_uri)
        config = await self._tokens.client_config(server.id)
        meta = await self.metadata(server)
        scope = " ".join(meta.scopes_supported) if meta.scopes_supported else None
        url = self._provider.authorize_url(
            meta,
            client_id=config.client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=pkce.challenge,
            scope=scope,
        )
        # UPO-8: record the issuer now, from validated metadata, never from the callback
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
