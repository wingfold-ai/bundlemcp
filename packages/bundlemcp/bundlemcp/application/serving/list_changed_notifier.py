"""Telling live streams that the tool surface they see has changed."""

from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent

LIST_CHANGED = {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}


class ListChangedNotifier:
    """Fans a bundle or endpoint change out to the streams this replica holds.

    Each replica walks only its own open streams, so together the replicas cover
    every client without any extra signalling. A stream's key says which
    endpoint and bundle it watches, so no session is loaded.
    """

    def __init__(self, registry: StreamRegistry) -> None:
        self._registry = registry

    async def on_invalidation(self, event: InvalidationEvent) -> None:
        # BND-7
        if event.entity_type not in ("bundle", "endpoint"):
            return
        for key in self._registry.broadcast_streams():
            affected = key.bundle_name if event.entity_type == "bundle" else key.endpoint_name
            if affected == event.key:
                self._registry.deliver_local(key.stream_id, LIST_CHANGED)
