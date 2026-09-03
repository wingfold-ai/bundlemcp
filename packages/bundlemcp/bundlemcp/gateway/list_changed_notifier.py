"""Telling live sessions that the tool surface they see has changed."""

from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.store.invalidation import InvalidationEvent
from bundlemcp.store.sessions import SessionStore

LIST_CHANGED = {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


class ListChangedNotifier:
    """Fans a bundle or endpoint change out to the sessions this replica streams to.

    Each replica walks only its own open streams, so together the replicas cover
    every session without any extra signalling.
    """

    def __init__(self, registry: StreamRegistry, sessions: SessionStore) -> None:
        self._registry = registry
        self._sessions = sessions

    async def on_invalidation(self, event: InvalidationEvent) -> None:
        # BND-7
        if event.entity_type not in ("bundle", "endpoint"):
            return
        for session_id in self._registry.broadcast_sessions():
            record = await self._sessions.load(session_id)
            if record is None:
                continue
            affected = record.bundle_name if event.entity_type == "bundle" else record.endpoint_name
            if affected == event.key:
                self._registry.deliver_local(session_id, LIST_CHANGED)
