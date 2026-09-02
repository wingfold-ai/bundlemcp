"""Server registry business logic, including upstream OAuth client configuration."""

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.crypto import token_cipher
from bundlemcp.models import BundleServer, McpServer, Tool, UpstreamOAuthClient
from bundlemcp.schemas import Page, ServerRead, ServerUpsert, ToolRead, UpstreamOAuthConfig
from bundlemcp.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PreconditionError,
    UnavailableError,
)
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation

if TYPE_CHECKING:
    from bundlemcp.gateway.discovery import DiscoveryService
    from bundlemcp.oauth.upstream_client import UpstreamTokenStore
    from bundlemcp.settings import Settings


def to_read(server: McpServer) -> ServerRead:
    data = server.model_dump()
    data["static_header_names"] = sorted(server.static_headers)  # SRV-3: names only
    return ServerRead.model_validate(data)


class ServerService:
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        *,
        discovery: "DiscoveryService | None" = None,
        settings: "Settings | None" = None,
        upstream_tokens: "UpstreamTokenStore | None" = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._discovery = discovery
        self._settings = settings
        self._upstream_tokens = upstream_tokens

    async def _by_name(self, name: str) -> McpServer | None:
        result = await self._db.execute(select(McpServer).where(McpServer.name == name))
        return result.scalar_one_or_none()

    async def _get(self, name: str) -> McpServer:
        server = await self._by_name(name)
        if server is None:
            raise NotFoundError("server not found")
        return server

    async def _invalidate(self, name: str, action: str) -> None:
        await publish_invalidation(
            self._redis, InvalidationEvent(entity_type="server", key=name, action=action)
        )

    async def list(self, *, offset: int, limit: int) -> Page[ServerRead]:
        total = (await self._db.execute(select(func.count()).select_from(McpServer))).scalar_one()
        rows = (
            await self._db.execute(
                select(McpServer)
                .order_by(McpServer.created_at, McpServer.id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
        return Page(items=[to_read(s) for s in rows], total=total, offset=offset, limit=limit)

    async def get(self, name: str) -> ServerRead:
        return to_read(await self._get(name))

    async def upsert(self, body: ServerUpsert) -> ServerRead:
        """Config-only upsert by natural key; idempotent; never blocks on probing."""
        server = await self._by_name(body.name)
        created = server is None
        if server is None:
            server = McpServer(name=body.name, url=body.url)
        server.description = body.description
        server.url = body.url
        if body.static_headers:  # write-only merge: empty dict keeps existing secrets
            server.static_headers = body.static_headers
        server.forward_headers = body.forward_headers
        server.auth_mode = body.auth_mode
        server.identity_mode = body.identity_mode
        server.send_identity_header = body.send_identity_header
        self._db.add(server)
        await self._db.commit()
        await self._db.refresh(server)
        await self._invalidate(body.name, "created" if created else "updated")
        # SRV-2: validate + discover best-effort; never blocks the API response.
        if self._discovery is not None:
            await self._discovery.schedule_probe(server.id)
        return to_read(server)

    async def delete(self, name: str) -> None:
        """Idempotent delete: a missing server still yields success (404 -> 204 semantics)."""
        server = await self._by_name(name)
        if server is not None:
            await self._db.delete(server)  # DOM-2 cascades tools + mappings
            await self._db.commit()
            await self._invalidate(name, "deleted")

    async def rename(self, name: str, new_name: str, *, force: bool) -> ServerRead:
        """Renaming a bundle member is rejected unless force acknowledges that
        client-visible tool names change."""
        server = await self._get(name)
        try:
            ServerUpsert(name=new_name, url=server.url)  # reuse name validation
        except ValidationError as exc:
            raise InvalidInputError(str(exc)) from None
        in_bundle = (
            await self._db.execute(
                select(BundleServer).where(BundleServer.server_id == server.id).limit(1)
            )
        ).scalar_one_or_none()
        if in_bundle is not None and not force:
            raise ConflictError(
                "server is a bundle member; renaming changes client-visible tool names — "
                "retry with force=true to acknowledge (SRV-5)"
            )
        server.name = new_name
        await self._db.commit()
        await self._db.refresh(server)
        await self._invalidate(new_name, "updated")
        return to_read(server)

    async def list_tools(self, name: str, *, offset: int, limit: int) -> Page[ToolRead]:
        server = await self._get(name)
        base = select(Tool).where(Tool.server_id == server.id)
        total = (
            await self._db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self._db.execute(base.order_by(Tool.name).offset(offset).limit(limit))
        ).scalars()
        return Page(
            items=[ToolRead.model_validate(t) for t in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def refresh_tools(self, name: str) -> dict[str, Any]:
        """Explicit refresh: runs tool discovery now and reports the result."""
        server = await self._get(name)
        if self._discovery is None:
            raise UnavailableError("discovery unavailable")
        result = await self._discovery.discover(server.id)
        return {"discovered": result.discovered, "changed": result.changed, "error": result.error}

    # --- upstream OAuth client config + status (spec 23, UPO-1/5) ---

    async def set_upstream_oauth(self, name: str, body: UpstreamOAuthConfig) -> dict[str, Any]:
        """Store the pre-registered client config. client_secret is write-only, encrypted."""
        server = await self._get(name)
        if self._settings is None or not self._settings.token_encryption_keys:
            raise PreconditionError("token encryption keys required for upstream OAuth (DEP-9)")
        cipher = token_cipher(self._settings)
        client = (
            await self._db.execute(
                select(UpstreamOAuthClient).where(UpstreamOAuthClient.server_id == server.id)
            )
        ).scalar_one_or_none()
        if client is None:
            client = UpstreamOAuthClient(server_id=server.id, client_id=body.client_id)
        client.client_id = body.client_id
        if body.client_secret:  # write-only: absent keeps the existing secret
            client.client_secret_encrypted = cipher.encrypt(body.client_secret)
        meta = dict(client.metadata_ or {})
        if body.authorization_url and body.token_url:
            meta["authorization_endpoint"] = body.authorization_url
            meta["token_endpoint"] = body.token_url
        client.metadata_ = meta
        self._db.add(client)
        await self._db.commit()
        return {"server": name, "client_id": body.client_id, "has_secret": bool(body.client_secret)}

    async def upstream_oauth_status(self, name: str) -> dict[str, Any]:
        """Report connection status only — never token values."""
        server = await self._get(name)
        if self._upstream_tokens is None:
            return {"identity_mode": server.identity_mode, "configured": False}
        shared = await self._upstream_tokens.status(server.id, None)
        return {"identity_mode": server.identity_mode, "shared": shared}

    async def disconnect_upstream_oauth(self, name: str) -> None:
        """Disconnect the shared upstream token."""
        server = await self._by_name(name)
        if server is None:
            return
        if self._upstream_tokens is not None:
            await self._upstream_tokens.disconnect(server.id, None)
