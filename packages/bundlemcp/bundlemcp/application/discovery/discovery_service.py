import asyncio
import uuid

import structlog

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork, UnitOfWorkFactory
from bundlemcp.application.contracts.upstream.upstream_probe import UpstreamProbe
from bundlemcp.application.discovery.connection_diagnoser import ConnectionDiagnoser
from bundlemcp.application.schemas import DiscoveryResult, DiscoverySweep
from bundlemcp.application.upstream_oauth.upstream_credential_resolver import (
    UpstreamCredentialResolver,
)
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.tool_sync import sync_tools
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured

DEFAULT_MAX_ATTEMPTS = 3  # UPS-4: consecutive failures before health_status=error
NOT_CONNECTED = "upstream not connected"
SWEEP_PAGE_SIZE = 100
# one hanging upstream must not hold up a sweep of every other server (UPS-23)
PROBE_TIMEOUT_SECONDS = 60

log = structlog.get_logger(__name__)


class DiscoveryService:
    """Probes one upstream MCP server and refreshes everything cached about it.

    A probe opens an MCP session and writes three things to the durable store:

    - **Tool definitions** — name, title, description, input schema and
      annotations into ``Tool``. Writes are hash-gated, so a tool whose
      definition is unchanged costs nothing; ``last_seen_at`` is touched on
      every sighting, so a tool that disappears upstream goes stale and stops
      being served rather than being deleted, keeping its curation.
    - **Advertised capabilities and protocol revision** — which of tools/
      prompts/resources/completions/logging the server supports, plus its
      listChanged and subscribe flags, taken from whatever the connection
      negotiated onto ``McpServer.capabilities``, and the negotiated MCP
      revision onto ``McpServer.protocol_version``. The snapshot is what
      capability gating reads when serving; the revision tells an operator
      which era the upstream speaks.
    - **Health** — consecutive failures are counted per server; at
      ``max_attempts`` the server flips to error with its last error recorded,
      and any success resets the streak.
    - **Connection state** — every probe records what it found out, classified
      from the upstream's HTTP response: ready, a refusal that names OAuth, a
      refusal that wants some other credential, a URL that is not MCP, an
      unreachable host. Unlike health it is updated on every probe.

    Caching all three is what lets bundles stay curatable and servable while
    an upstream is unreachable.

    A server behind upstream OAuth is probed with a connected account's token.
    Until an account is connected there is nothing to probe with; that is
    reported but not counted as a failure, because the upstream has not failed.
    When the tool set changes, every bundle the server belongs to is
    invalidated, which tells clients watching those bundles to list again.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        probe: UpstreamProbe,
        *,
        credentials: UpstreamCredentialResolver | None = None,
        diagnoser: ConnectionDiagnoser | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._units = units
        self._probe = probe
        self._credentials = credentials
        self._diagnoser = diagnoser or ConnectionDiagnoser(None)
        self._max_attempts = max_attempts
        self._failures: dict[uuid.UUID, int] = {}
        self._tasks: set[asyncio.Task] = set()

    async def schedule_probe(self, server_id: uuid.UUID, *, announce: bool = False) -> None:
        """Best-effort background probe; never blocks the caller."""
        task = asyncio.create_task(self._probe_quietly(server_id, announce=announce))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _probe_quietly(self, server_id: uuid.UUID, *, announce: bool) -> None:
        try:
            await self.discover(server_id, announce=announce)
        except Exception:  # pragma: no cover - defensive
            log.warning("discovery.probe_failed", server_id=str(server_id), exc_info=True)

    async def discover(self, server_id: uuid.UUID, *, announce: bool = False) -> DiscoveryResult:
        """Probe now and report how many tools were seen and how many changed.

        ``announce`` invalidates the server's bundles even when no tool changed,
        for a change the tool cache does not see, such as a user connecting the
        account that decides which tools they are offered.
        """
        async with self._units.open() as uow:
            server = await uow.servers.get(server_id)
            if server is None:
                return DiscoveryResult(error="server not found")
            try:
                headers = await self._headers(server)
            except (NeedsConnect, UpstreamOAuthNotConfigured):
                # UPS-17: nothing to probe with yet, which is not an upstream failure
                server.connection_state = ConnectionState.ACCOUNT_REQUIRED  # UPS-12
                uow.servers.add(server)
                if announce:
                    await self._announce(uow, server)
                await uow.commit()
                return DiscoveryResult(
                    error=NOT_CONNECTED, connection_state=ConnectionState.ACCOUNT_REQUIRED
                )
            try:
                async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
                    seen = await self._probe.probe(server, headers)
            except TimeoutError:
                return await self._record_failure(
                    uow,
                    server,
                    f"no answer within {PROBE_TIMEOUT_SECONDS}s",
                    ConnectionState.UNREACHABLE,
                )
            except ProbeFailure as failure:
                return await self._record_failure(
                    uow, server, str(failure), await self._state_of(server, failure)
                )
            except Exception as exc:
                return await self._record_failure(uow, server, str(exc), ConnectionState.ERROR)

            # UPS-22: snapshot the upstream's advertised capabilities for PROT-11,
            # and the revision negotiated with it (UPS-10).
            if seen.capabilities is not None:
                server.capabilities = seen.capabilities
            server.protocol_version = seen.protocol_version
            server.connection_state = ConnectionState.READY  # UPS-12
            uow.servers.add(server)

            existing = {t.name: t for t in await uow.tools.for_server(server.id)}
            staged, changed = sync_tools(server.id, existing, seen.tools, utcnow())
            for row in staged:
                uow.tools.add(row)
            await self._record_success(uow, server)
            if changed or announce:
                await self._announce(uow, server)  # BND-7: clients re-list the bundle
            await uow.commit()
            return DiscoveryResult(
                discovered=len(seen.tools), changed=changed, connection_state=ConnectionState.READY
            )

    async def discover_all(self) -> DiscoverySweep:
        """Probe every registered server, one after another.

        A server whose probe fails, or raises, is counted and skipped; the rest
        are still probed. A server not yet connected through upstream OAuth has
        nothing to probe with and is not counted as failed.
        """
        sweep = DiscoverySweep()
        for server_id in await self._server_ids():
            try:
                result = await self.discover(server_id)
            except Exception:
                log.warning("discovery.sweep_probe_failed", server_id=str(server_id), exc_info=True)
                sweep.failed += 1
            else:
                if result.error is not None and result.error != NOT_CONNECTED:
                    sweep.failed += 1
                sweep.changed += result.changed
            sweep.servers += 1
        return sweep

    async def _server_ids(self) -> list[uuid.UUID]:
        ids: list[uuid.UUID] = []
        async with self._units.open() as uow:
            while True:
                total, page = await uow.servers.page(offset=len(ids), limit=SWEEP_PAGE_SIZE)
                ids.extend(server.id for server in page)
                if not page or len(ids) >= total:
                    return ids

    async def _headers(self, server: McpServer) -> dict[str, str]:
        if self._credentials is None:
            return {}
        return await self._credentials.discovery_headers(server)

    @staticmethod
    async def _announce(uow: UnitOfWork, server: McpServer) -> None:
        """Invalidate every bundle the server belongs to, once the commit lands."""
        for membership in await uow.memberships.for_server(server.id):
            bundle = await uow.bundles.get(membership.bundle_id)
            if bundle is not None:
                uow.invalidate(
                    InvalidationEvent(entity_type="bundle", key=bundle.name, action="updated")
                )

    async def _state_of(self, server: McpServer, failure: ProbeFailure) -> ConnectionState:
        """The connection state a failure settles on for this server.

        A server that already sends a credential and is refused without an
        OAuth challenge has a bad credential; the OAuth chain is only followed
        for a server that sends none, so an expired key never reads as OAuth.
        """
        sends_credential = bool(server.static_headers) or server.uses_upstream_oauth
        if failure.state == ConnectionState.CREDENTIAL_REQUIRED and sends_credential:
            return failure.state
        return (await self._diagnoser.diagnose(server.url, failure)).state

    async def _record_failure(
        self, uow: UnitOfWork, server: McpServer, error: str, state: ConnectionState
    ) -> DiscoveryResult:
        count = self._failures.get(server.id, 0) + 1
        self._failures[server.id] = count
        # UPS-20: every failure is observable, not only the one that flips health
        log.warning(
            "discovery.failed",
            server=server.name,
            attempt=count,
            state=state.value,
            error=error[:200],
        )
        server.connection_state = state  # UPS-12: recorded on every probe
        if count >= self._max_attempts and server.health_status != HealthStatus.ERROR:
            server.health_status = HealthStatus.ERROR
            server.last_error = error[:500]
            log.warning("discovery.server_marked_error", server=server.name)  # UPS-4
        uow.servers.add(server)
        await uow.commit()
        return DiscoveryResult(error=error, connection_state=state)

    async def _record_success(self, uow: UnitOfWork, server: McpServer) -> None:
        self._failures.pop(server.id, None)
        if server.health_status != HealthStatus.OK:
            server.health_status = HealthStatus.OK  # UPS-4 self-heal
            server.last_error = None
            uow.servers.add(server)
