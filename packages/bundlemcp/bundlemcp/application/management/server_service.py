"""Server registry business logic."""

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.contracts.upstream.tool_discovery import ToolDiscovery
from bundlemcp.application.errors import ConflictError, PreconditionError
from bundlemcp.application.management.named_resource_service import NamedResourceService
from bundlemcp.application.management.per_user_upstream_check import PerUserUpstreamCheck
from bundlemcp.application.management.presented_name_check import PresentedNameCheck
from bundlemcp.application.management.upstream_credential_revocation import (
    UpstreamCredentialRevocation,
)
from bundlemcp.application.schemas import DiscoveryResult, Page, ServerRead, ServerUpsert, ToolRead
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.self_reference import (
    addresses_gateway_endpoint,
    self_reference_refusal,
)
from bundlemcp.domain.servers.url_change import UrlChange
from bundlemcp.domain.shared.resource_names import server_name as server_name_type
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant


class ServerService(NamedResourceService[McpServer, ServerRead]):
    def __init__(self, uow: UnitOfWork, discovery: ToolDiscovery, *, public_base: str) -> None:
        super().__init__(
            uow, repo=uow.servers, read_model=ServerRead, entity_type="server", label="server"
        )
        self._discovery = discovery
        self._policy = PerUserUpstreamCheck(uow)
        self._revocation = UpstreamCredentialRevocation(uow)
        self._public_base = public_base

    async def upsert(self, body: ServerUpsert, *, actor: Principal | None = None) -> ServerRead:
        """Config-only upsert by natural key; idempotent; never blocks on probing.

        Fields a caller leaves out keep their stored value on update and take
        their default on create; the send_identity_header default depends on
        whether the server is on the gateway's own network. The upstream is
        probed in the background on create, when the write changes what
        discovery depends on, or when the last probe did not succeed.

        Credentials never follow a server to a new URL: moving it to another
        resource revokes what was obtained for the old one, recorded against
        ``actor``, and moving it to another origin needs its static header
        values again.
        """
        server = await self._by_name(body.name)
        created = server is None
        previous_inputs = None if server is None else server.discovery_inputs
        if server is None:
            server = McpServer.register(body.name, body.changes())
        else:
            move = UrlChange(previous=server.url, current=body.url)
            if server.url != body.url:
                await self._ensure_not_a_member_pointing_at_the_gateway(server, body.url)
            if move.moves_origin and server.static_headers and not body.static_headers:
                raise ConflictError(
                    "the new url is on another origin; enter the static header values again so "
                    "the stored ones are not sent there (UPS-42)"
                )
            server.reconfigure(body.changes())
            await self._policy.ensure_identity_switch_allowed(server)
            await self._ensure_grant_allows_identity(server)
            await self._revocation.revoke(server, move, actor=actor)
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
        if client is not None and client.metadata_.grant == UpstreamGrant.CLIENT_CREDENTIALS:
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
        await PresentedNameCheck(self._uow).ensure_rename_allowed(server, new_name)
        return await self._rename(server, new_name, server_name_type)

    async def delete(self, name: str) -> None:
        """Idempotent; waits for a discovery of the server already running, on any replica.

        The discovery commits first and the delete then removes everything it stored, so the
        server cannot reappear; a discovery that starts meanwhile waits and finds no server.
        The server is looked up again once the wait is over, in case it was renamed.
        """
        server = await self._by_name(name)
        if server is None:
            return
        await self._uow.lock_server(server.id)
        await super().delete(name)

    async def list_tools(self, name: str, *, offset: int, limit: int) -> Page[ToolRead]:
        server = await self._get(name)
        page_slice = await self._uow.tools.page_for_server(server.id, offset=offset, limit=limit)
        return Page.of(
            page_slice, offset=offset, limit=limit, read=lambda tool: ToolRead.of(tool, server)
        )

    async def refresh_tools(self, name: str, *, prune: bool = False) -> DiscoveryResult:
        """Explicit refresh: runs tool discovery now and reports the result.

        ``prune`` also deletes the tools the server no longer lists, with their
        curation in every bundle, but only when the probe succeeds.
        """
        server = await self._get(name)
        return await self._discovery.discover(server.id, prune=prune)

    async def _ensure_not_a_member_pointing_at_the_gateway(
        self, server: McpServer, new_url: str
    ) -> None:
        """A member's URL may not be changed to one of the gateway's own endpoints."""
        if not addresses_gateway_endpoint(new_url, self._public_base):
            return
        if await self._uow.memberships.for_server(server.id):
            raise ConflictError(self_reference_refusal(server.name, new_url))
