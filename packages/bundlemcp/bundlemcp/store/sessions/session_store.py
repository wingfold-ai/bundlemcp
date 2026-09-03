import json
import secrets

from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import WatchError

from bundlemcp.store.redis import SESSION_KEY
from bundlemcp.store.sessions.session_record import SESSION_RECORD_VERSION, SessionRecord
from bundlemcp.store.sessions.upstream_binding import UpstreamBinding


class SessionStore:
    def __init__(self, redis: Redis, *, lifetime_seconds: int | None = 24 * 3600) -> None:
        self._redis = redis
        self._lifetime = lifetime_seconds  # None = no idle expiry (SES-10)

    @staticmethod
    def new_session_id() -> str:
        return secrets.token_urlsafe(24)

    def _key(self, session_id: str) -> str:
        return SESSION_KEY.format(session_id=session_id)

    async def create(self, record: SessionRecord) -> None:
        await self._write(record)

    async def load(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        data = json.loads(raw)
        if data.get("version") != SESSION_RECORD_VERSION:
            # DEP-6: unreadable future/ancient record => treat as expired, client re-inits
            await self._redis.delete(self._key(session_id))
            return None
        return SessionRecord(**data)

    async def touch(self, session_id: str) -> None:
        """Refresh idle TTL on activity (pings count as activity too)."""
        if self._lifetime is not None:
            await self._redis.expire(self._key(session_id), self._lifetime)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def set_binding(self, session_id: str, binding: UpstreamBinding) -> SessionRecord | None:
        """Atomically add/replace one binding (WATCH-based check-and-set)."""
        key = self._key(session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None:
                        await pipe.unwatch()
                        return None
                    record = SessionRecord(**json.loads(raw))
                    record.bindings[binding.server_name] = binding
                    pipe.multi()
                    await self._set(pipe, key, record)
                    await pipe.execute()
                    return record
                except WatchError:
                    continue

    async def _write(self, record: SessionRecord) -> None:
        key = self._key(record.session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.multi()
            await self._set(pipe, key, record)
            await pipe.execute()

    async def _set(self, pipe: Pipeline, key: str, record: SessionRecord) -> None:
        if self._lifetime is None:
            pipe.set(key, record.model_dump_json())
        else:
            pipe.set(key, record.model_dump_json(), ex=self._lifetime)
