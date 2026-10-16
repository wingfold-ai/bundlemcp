import uuid

from redis.asyncio import Redis

STREAK_KEY = "bmcp:health:streak:{server_id}"
# a streak nobody has added to for a day is forgotten rather than kept forever
STREAK_TTL_SECONDS = 86400


class ValkeyFailureStreak:
    """INCR and EXPIRE in one transaction, so concurrent failures on any replica all count."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def record_failure(self, server_id: uuid.UUID) -> int:
        key = STREAK_KEY.format(server_id=server_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, STREAK_TTL_SECONDS)
            count, _ = await pipe.execute()
        return int(count)

    async def reset(self, server_id: uuid.UUID) -> None:
        await self._redis.delete(STREAK_KEY.format(server_id=server_id))
