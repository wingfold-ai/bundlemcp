"""Session records in Redis (spec 30): a session is data, not an object.

Records are JSON values under SESSION_KEY with a TTL; any replica loads/serves
them (SES-2). Updates go through optimistic check-and-set (SES-1a).
"""

import json
import secrets
from typing import Any

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.asyncio.client import Pipeline
from redis.exceptions import WatchError

from bundlemcp.store.redis import SESSION_KEY

SESSION_RECORD_VERSION = 1  # DEP-6: bump only with cross-release read compat


class UpstreamBinding(BaseModel):
    """A session's lazy attachment to one upstream session (SES-6)."""

    server_name: str
    upstream_session_id: str | None = None
    identity_key: str | None = None  # caller sub + forwarded-credential hash (FWD-5)


class SessionRecord(BaseModel):
    version: int = SESSION_RECORD_VERSION
    session_id: str
    endpoint_name: str
    bundle_name: str
    auth_method: str  # oauth | api_key | none
    user_id: str | None = None
    user_email: str | None = None  # feeds MeterContext.email (MID-3)
    api_key_id: str | None = None
    protocol_version: str
    client_capabilities: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, UpstreamBinding] = Field(default_factory=dict)  # by server name


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
        """Refresh idle TTL on activity (SES-1; ping counts, PROT-8)."""
        if self._lifetime is not None:
            await self._redis.expire(self._key(session_id), self._lifetime)

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    async def set_binding(self, session_id: str, binding: UpstreamBinding) -> SessionRecord | None:
        """Atomically add/replace one binding (SES-1a: WATCH-based check-and-set)."""
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
