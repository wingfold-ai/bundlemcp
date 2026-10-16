from redis.asyncio import Redis

from bundlemcp.application.contracts.live_state.resource_subscriptions import (
    ResourceSubscription,
)

# streams subscribed to one resource, and the resources one stream holds
RESOURCE_KEY = "bmcp:rsub:{server}:{uri}"
STREAM_KEY = "bmcp:rsub-stream:{stream}"
# a stream that never says goodbye stops costing memory after a day
SUBSCRIPTION_TTL_SECONDS = 86400


class ValkeyResourceSubscriptionIndex:
    """Resource subscriptions as two Valkey sets per entry, so any replica can route an update.

    One set per resource names its streams, one set per stream names its
    resources; both expire a day after the last subscription touched them.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @staticmethod
    def _resource(subscription: ResourceSubscription) -> str:
        return RESOURCE_KEY.format(server=subscription.server_name, uri=subscription.uri)

    async def subscribe(self, stream_id: str, subscription: ResourceSubscription) -> None:
        resource = self._resource(subscription)
        stream = STREAM_KEY.format(stream=stream_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.sadd(resource, stream_id)
            pipe.expire(resource, SUBSCRIPTION_TTL_SECONDS)
            pipe.sadd(stream, subscription.model_dump_json())
            pipe.expire(stream, SUBSCRIPTION_TTL_SECONDS)
            await pipe.execute()

    async def unsubscribe(self, stream_id: str, subscription: ResourceSubscription) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.srem(self._resource(subscription), stream_id)
            pipe.srem(STREAM_KEY.format(stream=stream_id), subscription.model_dump_json())
            await pipe.execute()

    async def streams(self, subscription: ResourceSubscription) -> list[str]:
        members = await self._redis.smembers(self._resource(subscription))
        return sorted(m.decode() if isinstance(m, bytes) else m for m in members)

    async def of_stream(self, stream_id: str) -> list[ResourceSubscription]:
        members = await self._redis.smembers(STREAM_KEY.format(stream=stream_id))
        return sorted(
            (ResourceSubscription.model_validate_json(member) for member in members),
            key=lambda s: (s.server_name, s.uri),
        )

    async def drop_stream(self, stream_id: str) -> list[ResourceSubscription]:
        held = await self.of_stream(stream_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            for subscription in held:
                pipe.srem(self._resource(subscription), stream_id)
            pipe.delete(STREAM_KEY.format(stream=stream_id))
            await pipe.execute()
        return held
