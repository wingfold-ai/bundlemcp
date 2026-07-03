"""Tool discovery & cache sync + server health tracking."""

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.models import HealthStatus, McpServer, Tool, utcnow

log = structlog.get_logger(__name__)

DEFAULT_MAX_ATTEMPTS = 3  # SRV-4: consecutive failures before health_status=error


def tool_schema_hash(name: str, title: str | None, description: str | None,
                     input_schema: dict, annotations: dict | None) -> str:
    """Stable hash over the full definition; only changed hashes hit Postgres."""
    canonical = json.dumps(
        {
            "name": name,
            "title": title,
            "description": description,
            "input_schema": input_schema,
            "annotations": annotations,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class DiscoveryResult:
    discovered: int = 0
    changed: int = 0
    error: str | None = None


class DiscoveryService:
    """Connects to an upstream, syncs its tool definitions into Postgres.

    Failures are tracked per server: after `max_attempts` consecutive failures
    the server is marked error; any success resets it to ok.
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
            except Exception as exc:
                return await self._record_failure(db, server, str(exc))

            result = await self._sync_tools(db, server, upstream_tools)
            await self._record_success(db, server)
            return result

    async def _sync_tools(
        self, db: AsyncSession, server: McpServer, upstream_tools
    ) -> DiscoveryResult:
        existing = {
            t.name: t
            for t in (
                await db.execute(select(Tool).where(Tool.server_id == server.id))
            ).scalars()
        }
        changed = 0
        now = utcnow()
        for ut in upstream_tools:
            annotations = (
                ut.annotations.model_dump(exclude_none=True) if ut.annotations else None
            )
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
