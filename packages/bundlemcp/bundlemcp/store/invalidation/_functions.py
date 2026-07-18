from redis.asyncio import Redis

from bundlemcp.store.invalidation._common import INVALIDATION_CHANNEL
from bundlemcp.store.invalidation.invalidation_event import InvalidationEvent


async def publish_invalidation(redis: Redis, event: InvalidationEvent) -> None:
    await redis.publish(INVALIDATION_CHANNEL, event.model_dump_json())
