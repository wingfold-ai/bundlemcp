"""Cross-replica config invalidation.

Every config mutation publishes an event after commit; replicas subscribe and
drop affected local caches. Any code that caches config must subscribe to
this channel — caching without subscribing is forbidden.
"""

from bundlemcp.store.invalidation._common import INVALIDATION_CHANNEL, EntityType
from bundlemcp.store.invalidation._functions import publish_invalidation
from bundlemcp.store.invalidation.invalidation_event import InvalidationEvent
from bundlemcp.store.invalidation.invalidation_subscriber import InvalidationSubscriber

__all__ = [
    "INVALIDATION_CHANNEL",
    "EntityType",
    "InvalidationEvent",
    "InvalidationSubscriber",
    "publish_invalidation",
]
