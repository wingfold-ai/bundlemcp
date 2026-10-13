"""Telling live streams that a list they see has changed."""

from bundlemcp.application.contracts.live_state.stream_registry import StreamRegistry
from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent

TOOLS_LIST_CHANGED = "notifications/tools/list_changed"
PROMPTS_LIST_CHANGED = "notifications/prompts/list_changed"
RESOURCES_LIST_CHANGED = "notifications/resources/list_changed"

# Which list a change to each kind of record alters; the event key names a bundle,
# except for an endpoint change, whose key names the endpoint.
_CHANGED_LIST = {
    "bundle": TOOLS_LIST_CHANGED,  # BND-7
    "endpoint": TOOLS_LIST_CHANGED,
    "bundle_prompt": PROMPTS_LIST_CHANGED,  # BPR-11
    "bundle_resource": RESOURCES_LIST_CHANGED,
}


class ListChangedNotifier:
    """Fans a bundle or endpoint change out to the streams this replica holds.

    Each replica walks only its own open streams, so together the replicas cover
    every client without any extra signalling. A stream's key says which
    endpoint and bundle it watches, so no session is loaded.
    """

    def __init__(self, registry: StreamRegistry) -> None:
        self._registry = registry

    async def on_invalidation(self, event: InvalidationEvent) -> None:
        method = _CHANGED_LIST.get(event.entity_type)
        if method is None:
            return
        notification = {"jsonrpc": "2.0", "method": method}
        for key in self._registry.broadcast_streams():
            affected = key.endpoint_name if event.entity_type == "endpoint" else key.bundle_name
            if affected == event.key:
                self._registry.deliver_local(key.stream_id, notification)
