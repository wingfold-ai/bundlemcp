"""Letting go of what an expired session held upstream."""

import structlog

from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscriptions,
)
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.upstream.upstream_session_pool import UpstreamSessionPool
from bundlemcp.domain.sessions.session_record import SessionRecord

log = structlog.get_logger(__name__)


class ExpiredSessionRelease:
    """Ends the upstream sessions an expired session was bound to, and its subscriptions.

    Nobody is calling, so each upstream is asked with the server's own headers
    only; one that wants the caller's credentials to end a session refuses,
    and expires it in its own time.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        upstream_sessions: UpstreamSessionPool,
        subscriptions: ResourceSubscriptions,
    ) -> None:
        self._units = units
        self._upstream_sessions = upstream_sessions
        self._subscriptions = subscriptions

    async def __call__(self, record: SessionRecord) -> None:
        await self._subscriptions.drop_stream(record.session_id)
        bound = [b for b in record.bindings.values() if b.upstream_session_id is not None]
        if not bound:
            return
        async with self._units.open() as uow:
            servers = {b.server_name: await uow.servers.by_name(b.server_name) for b in bound}
        for binding in bound:
            server = servers[binding.server_name]
            if server is None:
                continue
            try:
                await self._upstream_sessions.end(server, binding, {})
            except Exception:
                log.info("upstream_session.end_failed", server=server.name, exc_info=True)
