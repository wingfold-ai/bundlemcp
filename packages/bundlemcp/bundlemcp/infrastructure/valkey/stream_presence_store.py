import uuid

from redis.asyncio import Redis
from redis.asyncio.client import Pipeline

HOLDER_KEY = "bmcp:holder:{stream_id}"


class ValkeyStreamPresence:
    """One key per held stream naming the replica that holds it, expiring unless refreshed.

    ``hold_seconds`` should outlive a missed refresh or two, and no more: a
    holder that died is believed for that long.
    """

    def __init__(self, redis: Redis, *, hold_seconds: int, replica_id: str | None = None) -> None:
        self._redis = redis
        self._hold_seconds = hold_seconds
        self._replica_id = replica_id or uuid.uuid4().hex

    def _key(self, stream_id: str) -> str:
        return HOLDER_KEY.format(stream_id=stream_id)

    async def hold(self, stream_id: str) -> None:
        await self._redis.set(self._key(stream_id), self._replica_id, ex=self._hold_seconds)

    async def release(self, stream_id: str) -> None:
        key = self._key(stream_id)

        async def release_own(pipe: Pipeline) -> None:
            if await pipe.get(key) != self._replica_id:
                return  # the client reconnected elsewhere; that hold is not ours
            pipe.multi()
            pipe.delete(key)

        await self._redis.transaction(release_own, key)

    async def is_held(self, stream_id: str) -> bool:
        return bool(await self._redis.exists(self._key(stream_id)))
