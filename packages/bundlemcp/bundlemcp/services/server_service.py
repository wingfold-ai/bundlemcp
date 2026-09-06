"""Server registry business logic."""

from bundlemcp.models import BundleServer, McpServer, Tool
from bundlemcp.schemas import DiscoveryResult, Page, ServerRead, ServerUpsert, ToolRead
from bundlemcp.schemas.resource_names import server_name as server_name_type
from bundlemcp.services.errors import ConflictError
from bundlemcp.services.named_resource_service import NamedResourceService
from bundlemcp.services.per_user_upstream_policy import PerUserUpstreamPolicy
from bundlemcp.services.tool_discovery import ToolDiscovery
from bundlemcp.store import Repository, UnitOfWork


class ServerService(NamedResourceService[McpServer, ServerRead]):
    def __init__(self, uow: UnitOfWork, discovery: ToolDiscovery) -> None:
        super().__init__(
            uow, entity=McpServer, read_model=ServerRead, entity_type="server", label="server"
        )
        self._discovery = discovery
        self._memberships = Repository(uow.session, BundleServer)
        self._tools = Repository(uow.session, Tool)
        self._policy = PerUserUpstreamPolicy(uow.session)

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
        server.protocol_mode = body.protocol_mode  # SRV-10
        if not created:
            await self._policy.ensure_identity_switch_allowed(server)
        read = await self._save(server, name=body.name, created=created)
        # SRV-2: validate + discover best-effort; never blocks the API response.
        await self._discovery.schedule_probe(server.id)
        return read

    async def rename(self, name: str, new_name: str, *, force: bool) -> ServerRead:
        """Renaming a bundle member is rejected unless force acknowledges that
        client-visible tool names change."""
        server = await self._get(name)
        in_bundle = await self._memberships.one(BundleServer.server_id == server.id)
        if in_bundle is not None and not force:
            raise ConflictError(
                "server is a bundle member; renaming changes client-visible tool names — "
                "retry with force=true to acknowledge (SRV-5)"
            )
        return await self._rename(server, new_name, server_name_type)

    async def list_tools(self, name: str, *, offset: int, limit: int) -> Page[ToolRead]:
        server = await self._get(name)
        total, rows = await self._tools.page(
            Tool.server_id == server.id, offset=offset, limit=limit, order_by=(Tool.name,)
        )
        return Page.of(rows, total, offset=offset, limit=limit, read=ToolRead.from_entity)

    async def refresh_tools(self, name: str) -> DiscoveryResult:
        """Explicit refresh: runs tool discovery now and reports the result."""
        server = await self._get(name)
        return await self._discovery.discover(server.id)
