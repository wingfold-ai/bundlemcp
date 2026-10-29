from collections.abc import Callable
from datetime import datetime

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline

from bundlemcp.domain.sessions.session_lifetime import SessionLifetime
from bundlemcp.domain.sessions.session_record import SESSION_RECORD_VERSION, SessionRecord
from bundlemcp.domain.sessions.upstream_binding import UpstreamBinding
from bundlemcp.domain.shared.clock import Clock

log = structlog.get_logger(__name__)

SESSION_KEY = "bmcp:session:{session_id}"  # session record (JSON)
# session ids scored by their last activity (epoch seconds), for the sweeper
ACTIVITY_INDEX = "bmcp:sessions:active"


class ValkeySessionStore:
    """Session records as JSON, with an activity index of the ones that can expire.

    The record's TTL is the idle lifetime plus the sweeper's margin, set again
    at every activity; a lifetime of 0 stores it without one, and leaves it
    out of the index. Updates that are not activity keep the TTL they find.
    """

    def __init__(self, redis: Redis, *, clock: Clock) -> None:
        self._redis = redis
        self._clock = clock

    def _key(self, session_id: str) -> str:
        return SESSION_KEY.format(session_id=session_id)

    async def create(self, record: SessionRecord, lifetime: SessionLifetime) -> None:
        key = self._key(record.session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.multi()
            self._set_live(pipe, key, record, lifetime)
            await pipe.execute()

    async def load(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        record = self._parse(raw)
        if record is None:
            # an unreadable future/ancient record is treated as expired;
            # the client re-initializes.
            await self._redis.delete(self._key(session_id))
        return record

    async def touch(self, session_id: str, lifetime: SessionLifetime) -> None:
        """Record the activity and restart the lifetime (pings count as activity too)."""
        key = self._key(session_id)

        async def read_touch_write(pipe: Pipeline) -> None:
            raw = await pipe.get(key)
            record = self._parse(raw) if raw is not None else None
            if record is None:
                return
            record.last_active_at = self._clock.now()
            pipe.multi()
            self._set_live(pipe, key, record, lifetime)

        await self._redis.transaction(read_touch_write, key)

    async def delete(self, session_id: str) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(self._key(session_id))
            pipe.zrem(ACTIVITY_INDEX, session_id)
            await pipe.execute()

    async def idle_since(self, cutoff: datetime, *, limit: int) -> list[str]:
        return list(
            await self._redis.zrangebyscore(
                ACTIVITY_INDEX, "-inf", cutoff.timestamp(), start=0, num=limit
            )
        )

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
        # concurrent binding updates must not lose one another
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

    @staticmethod
    def _set(pipe: Pipeline, key: str, record: SessionRecord) -> None:
        """Write a change that is not activity: the record keeps the TTL it had."""
        pipe.set(key, record.model_dump_json(), keepttl=True)

    @staticmethod
    def _set_live(
        pipe: Pipeline, key: str, record: SessionRecord, lifetime: SessionLifetime
    ) -> None:
        """Write the record as active now, with the lifetime's TTL and index entry."""
        if not lifetime.expires:
            pipe.set(key, record.model_dump_json())  # no TTL: lives until deleted
            pipe.zrem(ACTIVITY_INDEX, record.session_id)
            return
        pipe.set(key, record.model_dump_json(), ex=lifetime.store_ttl)
        pipe.zadd(ACTIVITY_INDEX, {record.session_id: record.last_active_at.timestamp()})

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
