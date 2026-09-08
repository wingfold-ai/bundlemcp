from redis.asyncio import Redis


class ValkeyRefreshLock:
    """SET NX with an expiry: the lock frees itself if its holder dies mid-refresh."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def acquire(self, key: str, *, ttl_seconds: int) -> bool:
        return bool(await self._redis.set(key, "1", nx=True, ex=ttl_seconds))

    async def release(self, key: str) -> None:
        await self._redis.delete(key)
