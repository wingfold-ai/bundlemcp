import asyncio
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from bundlemcp.gateway.discovery.tool_schema_hash import tool_schema_hash
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.models import HealthStatus, McpServer, Tool, utcnow
from bundlemcp.schemas import DiscoveryResult

DEFAULT_MAX_ATTEMPTS = 3  # SRV-4: consecutive failures before health_status=error

log = structlog.get_logger(__name__)


class DiscoveryService:
    """Probes one upstream MCP server and refreshes everything cached about it.

    A probe opens an MCP session and writes three things to Postgres:

    - **Tool definitions** — name, title, description, input schema and
      annotations into ``Tool``. Writes are hash-gated, so a tool whose
      definition is unchanged costs nothing; ``last_seen_at`` is touched on
      every sighting, so a tool that disappears upstream goes stale and stops
      being served rather than being deleted, keeping its curation.
    - **Advertised capabilities** — which of tools/prompts/resources/
      completions/logging the server supports, plus its listChanged and
      subscribe flags, taken from the upstream ``initialize`` result onto
      ``McpServer.capabilities``. That snapshot is what capability gating
      reads when serving.
    - **Health** — consecutive failures are counted per server; at
      ``max_attempts`` the server flips to error with its last error recorded,
      and any success resets the streak.

    Caching all three is what lets bundles stay curatable and servable while
    an upstream is unreachable.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client_factory: ClientFactory,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._sessions = session_factory
        self._client_factory = client_factory
        self._max_attempts = max_attempts
        self._failures: dict[uuid.UUID, int] = {}
        self._tasks: set[asyncio.Task] = set()

    async def schedule_probe(self, server_id: uuid.UUID) -> None:
        """Best-effort background probe; never blocks the caller."""
        task = asyncio.create_task(self._probe_quietly(server_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _probe_quietly(self, server_id: uuid.UUID) -> None:
        try:
            await self.discover(server_id)
        except Exception:  # pragma: no cover - defensive
            log.warning("discovery.probe_failed", server_id=str(server_id), exc_info=True)

    async def discover(self, server_id: uuid.UUID) -> DiscoveryResult:
        """Probe now and report how many tools were seen and how many changed."""
        async with self._sessions() as db:
            server = (
                await db.execute(select(McpServer).where(McpServer.id == server_id))
            ).scalar_one_or_none()
            if server is None:
                return DiscoveryResult(error="server not found")

            try:
                client = self._client_factory(server, {})
                async with client:
                    upstream_tools = await client.list_tools()
                    init = client.initialize_result
            except Exception as exc:
                return await self._record_failure(db, server, str(exc))

            # DISC-6: snapshot the upstream's advertised capabilities for PROT-11.
            if init is not None and init.capabilities is not None:
                server.capabilities = init.capabilities.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
                db.add(server)
            result = await self._sync_tools(db, server, upstream_tools)
            await self._record_success(db, server)
            return result

    async def _sync_tools(
        self, db: AsyncSession, server: McpServer, upstream_tools
    ) -> DiscoveryResult:
        existing = {
            t.name: t
            for t in (await db.execute(select(Tool).where(Tool.server_id == server.id))).scalars()
        }
        changed = 0
        now = utcnow()
        for ut in upstream_tools:
            annotations = ut.annotations.model_dump(exclude_none=True) if ut.annotations else None
            input_schema = ut.inputSchema or {}
            digest = tool_schema_hash(ut.name, ut.title, ut.description, input_schema, annotations)
            row = existing.get(ut.name)
            if row is None:
                db.add(
                    Tool(
                        server_id=server.id,
                        name=ut.name,
                        title=ut.title,
                        description=ut.description,
                        input_schema=input_schema,
                        annotations=annotations,
                        schema_hash=digest,
                        last_seen_at=now,
                    )
                )
                changed += 1
            else:
                if row.schema_hash != digest:  # DISC-2: write only on change
                    row.title = ut.title
                    row.description = ut.description
                    row.input_schema = input_schema
                    row.annotations = annotations
                    row.schema_hash = digest
                    changed += 1
                row.last_seen_at = now  # DISC-3: vanished tools keep old last_seen_at
                db.add(row)
        await db.commit()
        return DiscoveryResult(discovered=len(upstream_tools), changed=changed)

    async def _record_failure(
        self, db: AsyncSession, server: McpServer, error: str
    ) -> DiscoveryResult:
        count = self._failures.get(server.id, 0) + 1
        self._failures[server.id] = count
        if count >= self._max_attempts and server.health_status != HealthStatus.ERROR:
            server.health_status = HealthStatus.ERROR
            server.last_error = error[:500]
            db.add(server)
            await db.commit()
            log.warning("discovery.server_marked_error", server=server.name)  # SRV-4
        return DiscoveryResult(error=error)

    async def _record_success(self, db: AsyncSession, server: McpServer) -> None:
        self._failures.pop(server.id, None)
        if server.health_status != HealthStatus.OK:
            server.health_status = HealthStatus.OK  # SRV-4 self-heal
            server.last_error = None
            db.add(server)
            await db.commit()
