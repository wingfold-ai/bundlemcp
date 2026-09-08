"""Configuring a server's pre-registered upstream OAuth client, and reading its connection state."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.upstream_connection_registry import (
    UpstreamConnectionRegistry,
)
from bundlemcp.application.errors import NotFoundError, PreconditionError
from bundlemcp.application.schemas import (
    UpstreamOAuthClientRead,
    UpstreamOAuthConfig,
    UpstreamOAuthStatusRead,
)
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.upstream_oauth_client import UpstreamOAuthClient


class UpstreamOAuthConfigService:
    """The client secret is write-only and stored encrypted; status never carries tokens."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        cipher: SecretCipher | None,
        connections: UpstreamConnectionRegistry,
    ) -> None:
        # cipher is None exactly when no token encryption keys are configured (DEP-9)
        self._uow = uow
        self._cipher = cipher
        self._connections = connections
        self._servers = uow.servers
        self._clients = uow.upstream_clients

    async def _server(self, name: str) -> McpServer:
        server = await self._servers.by_name(name)
        if server is None:
            raise NotFoundError("server not found")
        return server

    async def set_client(self, name: str, body: UpstreamOAuthConfig) -> UpstreamOAuthClientRead:
        server = await self._server(name)
        if self._cipher is None:
            raise PreconditionError("token encryption keys required for upstream OAuth (DEP-9)")
        client = await self._clients.for_server(server.id)
        if client is None:
            client = UpstreamOAuthClient(server_id=server.id, client_id=body.client_id)
        client.client_id = body.client_id
        if body.client_secret:  # write-only: absent keeps the existing secret
            client.client_secret_encrypted = self._cipher.encrypt(body.client_secret)
        metadata = dict(client.metadata_ or {})
        if body.authorization_url and body.token_url:
            metadata["authorization_endpoint"] = body.authorization_url
            metadata["token_endpoint"] = body.token_url
        client.metadata_ = metadata
        self._clients.add(client)
        await self._uow.commit()
        return UpstreamOAuthClientRead(
            server=name, client_id=body.client_id, has_secret=bool(body.client_secret)
        )

    async def status(self, name: str) -> UpstreamOAuthStatusRead:
        server = await self._server(name)
        client = await self._clients.for_server(server.id)
        metadata = (client.metadata_ if client else None) or {}
        registration = {
            "client_id": client.client_id if client else None,
            "authorization_url": metadata.get("authorization_endpoint"),
            "token_url": metadata.get("token_endpoint"),
        }
        if not self._connections.configured:
            return UpstreamOAuthStatusRead(
                identity_mode=server.identity_mode, configured=False, **registration
            )
        return UpstreamOAuthStatusRead(
            identity_mode=server.identity_mode,
            configured=True,
            shared=await self._connections.status(server.id, None),
            **registration,
        )

    async def disconnect(self, name: str) -> None:
        """Forget the shared connection; idempotent for an unknown server."""
        server = await self._servers.by_name(name)
        if server is not None:
            await self._connections.disconnect(server.id, None)
