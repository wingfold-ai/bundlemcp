"""Server registry business logic."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.contracts.upstream.tool_discovery import ToolDiscovery
from bundlemcp.application.errors import ConflictError, PreconditionError
from bundlemcp.application.management.named_resource_service import NamedResourceService
from bundlemcp.application.management.per_user_upstream_check import PerUserUpstreamCheck
from bundlemcp.application.schemas import DiscoveryResult, Page, ServerRead, ServerUpsert, ToolRead
from bundlemcp.domain.servers.internal_host import is_internal_host
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.shared.resource_names import server_name as server_name_type
from bundlemcp.domain.upstream_oauth.upstream_client_config import GRANT_KEY
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant


class ServerService(NamedResourceService[McpServer, ServerRead]):
    def __init__(self, uow: UnitOfWork, discovery: ToolDiscovery) -> None:
        super().__init__(
            uow, repo=uow.servers, read_model=ServerRead, entity_type="server", label="server"
        )
        self._discovery = discovery
        self._policy = PerUserUpstreamCheck(uow)

    async def upsert(self, body: ServerUpsert) -> ServerRead:
        """Config-only upsert by natural key; idempotent; never blocks on probing.

        Fields a caller leaves out keep their stored value on update and take
        their default on create; the send_identity_header default depends on
        whether the server is on the gateway's own network. The upstream is
        probed in the background on create, when the write changes what
        discovery depends on, or when the last probe did not succeed.
        """
        server = await self._by_name(body.name)
        created = server is None
        previous_inputs = None if server is None else server.discovery_inputs
        if server is None:
            server = McpServer(
                name=body.name,
                url=body.url,
                send_identity_header=(
                    body.send_identity_header
                    if body.send_identity_header is not None
                    else is_internal_host(body.url)
                ),
            )
        server.description = body.description
        server.url = body.url
        if body.static_headers:  # write-only merge: empty dict keeps existing secrets
            server.static_headers = body.static_headers
        server.forward_headers = body.forward_headers
        # none vs static_headers is whatever the stored headers say
        server.auth_mode = body.auth_mode.settled(has_static_headers=bool(server.static_headers))
        server.identity_mode = body.identity_mode
        if body.send_identity_header is not None:
            server.send_identity_header = body.send_identity_header
        if body.protocol_mode is not None:
            server.protocol_mode = body.protocol_mode
        if not created:
            await self._policy.ensure_identity_switch_allowed(server)
            await self._ensure_grant_allows_identity(server)
        read = await self._save(server, name=body.name, created=created)
        # validate + discover best-effort; never blocks the API response. An
        # unchanged re-apply to a working server stays off the upstream (ADR-0043).
        if previous_inputs != server.discovery_inputs or not server.last_probe_succeeded:
            await self._discovery.schedule_probe(server.id)
        return read

    async def _ensure_grant_allows_identity(self, server: McpServer) -> None:
        """A client-credentials client authorizes the gateway, never an individual user."""
        if not (server.uses_upstream_oauth and server.is_per_user):
            return
        client = await self._uow.upstream_clients.for_server(server.id)
        if client is not None and (client.metadata_ or {}).get(GRANT_KEY) == (
            UpstreamGrant.CLIENT_CREDENTIALS
        ):
            raise PreconditionError(
                "the server's upstream OAuth client uses client credentials, which cannot act "
                "for individual users; store an authorization-code client first (UPS-35)"
            )

    async def rename(self, name: str, new_name: str, *, force: bool) -> ServerRead:
        """Renaming a bundle member is rejected unless force acknowledges that
        client-visible tool names change."""
        server = await self._get(name)
        if await self._uow.memberships.for_server(server.id) and not force:
            raise ConflictError(
                "server is a bundle member; renaming changes client-visible tool names — "
                "retry with force=true to acknowledge (UPS-5)"
            )
        return await self._rename(server, new_name, server_name_type)

    async def list_tools(self, name: str, *, offset: int, limit: int) -> Page[ToolRead]:
        server = await self._get(name)
        total, rows = await self._uow.tools.page_for_server(server.id, offset=offset, limit=limit)
        return Page.of(rows, total, offset=offset, limit=limit, read=ToolRead.from_entity)

    async def refresh_tools(self, name: str) -> DiscoveryResult:
        """Explicit refresh: runs tool discovery now and reports the result."""
        server = await self._get(name)
        return await self._discovery.discover(server.id)
