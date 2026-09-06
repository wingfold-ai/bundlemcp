"""Cross-replica config invalidation.

Every config mutation publishes an event after commit; replicas subscribe and
drop affected local caches. Any code that caches config must subscribe to
this channel — caching without subscribing is forbidden.
"""

from bundlemcp.store.invalidation.invalidation_event import EntityType, InvalidationEvent
from bundlemcp.store.invalidation.invalidation_subscriber import InvalidationSubscriber
from bundlemcp.store.invalidation.publish_invalidation import (
    INVALIDATION_CHANNEL,
    publish_invalidation,
)

__all__ = [
    "INVALIDATION_CHANNEL",
    "EntityType",
    "InvalidationEvent",
    "InvalidationSubscriber",
    "publish_invalidation",
]
