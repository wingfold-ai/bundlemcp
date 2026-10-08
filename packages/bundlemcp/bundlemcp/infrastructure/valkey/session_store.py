from collections.abc import Callable

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline

from bundlemcp.domain.sessions.session_record import SESSION_RECORD_VERSION, SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding

log = structlog.get_logger(__name__)

SESSION_KEY = "bmcp:session:{session_id}"  # SES-1 session record (JSON)


class ValkeySessionStore:
    def __init__(self, redis: Redis, *, lifetime_seconds: int | None = 24 * 3600) -> None:
        self._redis = redis
        self._lifetime = lifetime_seconds  # None = no idle expiry (SES-10)

    def _key(self, session_id: str) -> str:
        return SESSION_KEY.format(session_id=session_id)

    async def create(self, record: SessionRecord) -> None:
        await self._write(record)

    async def load(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        record = self._parse(raw)
        if record is None:
            # DEP-6: an unreadable future/ancient record is treated as expired;
            # the client re-initializes.
            await self._redis.delete(self._key(session_id))
        return record

    async def touch(self, session_id: str) -> None:
        """Refresh idle TTL on activity (pings count as activity too)."""
        if self._lifetime is not None:
            await self._redis.expire(self._key(session_id), self._lifetime)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def set_binding(self, session_id: str, binding: UpstreamBinding) -> SessionRecord | None:
        """Atomically add/replace one binding."""

        def bind(record: SessionRecord) -> None:
            record.bindings[binding.server_name] = binding

        return await self._update(session_id, bind)

    async def set_log_level(self, session_id: str, level: str) -> SessionRecord | None:
        """Atomically record the log level the client asked for."""

        def set_level(record: SessionRecord) -> None:
            record.log_level = level

        return await self._update(session_id, set_level)

    async def _update(
        self, session_id: str, mutate: Callable[[SessionRecord], None]
    ) -> SessionRecord | None:
        # SES-1a: concurrent binding updates must not lose one another
        """Apply one change to a record under WATCH-based check-and-set.

        ``Redis.transaction`` owns the WATCH, MULTI, EXEC and the retry when the
        key changed underneath the read; the callable only reads, mutates and
        queues the write.
        """
        key = self._key(session_id)

        async def read_mutate_write(pipe: Pipeline) -> SessionRecord | None:
            raw = await pipe.get(key)
            record = self._parse(raw) if raw is not None else None
            if record is None:
                return None
            mutate(record)
            pipe.multi()
            self._set(pipe, key, record)
            return record

        return await self._redis.transaction(read_mutate_write, key, value_from_callable=True)

    async def _write(self, record: SessionRecord) -> None:
        key = self._key(record.session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.multi()
            self._set(pipe, key, record)
            await pipe.execute()

    def _set(self, pipe: Pipeline, key: str, record: SessionRecord) -> None:
        if self._lifetime is None:
            pipe.set(key, record.model_dump_json())
        else:
            pipe.set(key, record.model_dump_json(), ex=self._lifetime)

    @staticmethod
    def _parse(raw: str) -> SessionRecord | None:
        """A stored record, or None when its shape or version is not this build's."""
        try:
            record = SessionRecord.model_validate_json(raw)
        except ValidationError:
            log.warning("session.malformed")
            return None
        if record.version != SESSION_RECORD_VERSION:
            return None
        return record
