"""Announcing a config change to the other replicas."""

from redis.asyncio import Redis

from bundlemcp.store.invalidation.invalidation_event import InvalidationEvent
from bundlemcp.store.redis import INVALIDATION_CHANNEL


async def publish_invalidation(redis: Redis, event: InvalidationEvent) -> None:
    """Publish after commit, so subscribers never read a pre-commit state."""
    await redis.publish(INVALIDATION_CHANNEL, event.model_dump_json())
