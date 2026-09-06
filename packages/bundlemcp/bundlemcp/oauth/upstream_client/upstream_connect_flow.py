"""The interactive connect: send the user upstream, exchange the code they bring back."""

import uuid

from bundlemcp.crypto import PkcePair
from bundlemcp.models import McpServer
from bundlemcp.oauth.upstream_client.authorize_start import AuthorizeStart
from bundlemcp.oauth.upstream_client.upstream_metadata import UpstreamMetadata
from bundlemcp.oauth.upstream_client.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.oauth.upstream_client.upstream_token_repository import UpstreamTokenRepository


class UpstreamConnectFlow:
    def __init__(self, tokens: UpstreamTokenRepository, provider: UpstreamOAuthProvider) -> None:
        self._tokens = tokens
        self._provider = provider

    async def metadata(self, server: McpServer) -> UpstreamMetadata:
        """Configured endpoints win; otherwise discover them from the server's origin."""
        config = await self._tokens.client_config(server.id)
        cached = config.metadata
        if cached.get("authorization_endpoint") and cached.get("token_endpoint"):
            return UpstreamMetadata(**cached)
        return await self._provider.discover(server.url)

    async def begin(self, server: McpServer, redirect_uri: str, state: str) -> AuthorizeStart:
        # UPO-1/3: PKCE S256 connect
        pkce = PkcePair.generate()
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
