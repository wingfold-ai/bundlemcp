import uuid

import structlog

from bundlemcp.application.contracts.live_state.failure_streak import FailureStreak
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.serving.runtime_config import RuntimeConfig
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.mcp_server import McpServer

log = structlog.get_logger(__name__)


class UpstreamHealth:
    """Turns "connecting to this upstream failed" or "it answered" into ``health_status``.

    The consecutive-failure streak is live state shared by every replica, so
    failures seen anywhere add up. After ``server_error_attempts`` of them in a
    row (read on each failure, so a change applies without a restart) the
    server is marked ``error`` with the last message; the next answer resets
    the streak and heals it. Every source reports here: discovery probes and
    live calls alike.

    Counting is best effort. When the streak cannot be read or written the
    failure is logged and health is left as it is; a call or a probe never
    fails because health could not be updated.
    """

    def __init__(
        self, units: UnitOfWorkFactory, streak: FailureStreak, runtime_config: RuntimeConfig
    ) -> None:
        self._units = units
        self._streak = streak
        self._runtime_config = runtime_config

    async def apply_failure(self, server: McpServer, error: str) -> int:
        """Count a failure against ``server`` and mark it ``error`` once the streak is long enough.

        Changes the given server only; the caller persists it. Returns the
        streak, or 0 when it could not be counted.
        """
        try:
            count = await self._streak.record_failure(server.id)
        except Exception:
            log.warning("health.streak_unavailable", server=server.name, exc_info=True)
            return 0
        attempts = (await self._runtime_config.settings()).server_error_attempts
        if count >= attempts and server.health_status != HealthStatus.ERROR:
            server.health_status = HealthStatus.ERROR
            server.last_error = error[:500]
            log.warning("discovery.server_marked_error", server=server.name, attempts=count)
        return count

    async def apply_success(self, server: McpServer) -> bool:
        """End the streak and heal ``server``; whether the server changed and needs saving."""
        try:
            await self._streak.reset(server.id)
        except Exception:
            log.warning("health.streak_unavailable", server=server.name, exc_info=True)
        if server.health_status == HealthStatus.OK:
            return False
        server.health_status = HealthStatus.OK
        server.last_error = None
        return True

    async def failed(self, server_id: uuid.UUID, error: str) -> None:
        """A live call could not reach the upstream: count it, saving only a status change."""
        async with self._units.open() as uow:
            server = await uow.servers.get(server_id)
            if server is None:
                return
            before = server.health_status
            await self.apply_failure(server, error)
            if server.health_status != before:
                uow.servers.add(server)
                await uow.commit()

    async def succeeded(self, server_id: uuid.UUID, known: HealthStatus) -> None:
        """A live call got an MCP answer: end the streak, and heal the server if it was not ok.

        ``known`` is the status the caller already holds, so a healthy server
        costs one streak reset and no database access.
        """
        if known == HealthStatus.OK:
            try:
                await self._streak.reset(server_id)
            except Exception:
                log.warning("health.streak_unavailable", server_id=str(server_id), exc_info=True)
            return
        async with self._units.open() as uow:
            server = await uow.servers.get(server_id)
            if server is not None and await self.apply_success(server):
                uow.servers.add(server)
                await uow.commit()
