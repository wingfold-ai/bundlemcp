"""Announcing a config change to the other replicas."""

from redis.asyncio import Redis

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent

INVALIDATION_CHANNEL = "bmcp:invalidate"  # SES-17 config invalidation events


async def publish_invalidation(redis: Redis, event: InvalidationEvent) -> None:
    """Publish after commit, so subscribers never read a pre-commit state."""
    await redis.publish(INVALIDATION_CHANNEL, event.model_dump_json())
