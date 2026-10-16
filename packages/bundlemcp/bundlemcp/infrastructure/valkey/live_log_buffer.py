import json

from redis.asyncio import Redis

from bundlemcp.application.contracts.live_state.live_log_entry import LiveLogEntry

LIVE_LOG_KEY = "bmcp:logs"
LIVE_LOG_CAP = 10_000  # approximate: the stream is trimmed in whole nodes


class ValkeyLiveLogBuffer:
    """The live log as a Valkey stream, trimmed to about the newest ten thousand entries."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def append(self, entries: list[LiveLogEntry]) -> None:
        if not entries:
            return
        async with self._redis.pipeline(transaction=False) as pipe:
            for entry in entries:
                pipe.xadd(
                    LIVE_LOG_KEY,
                    {"entry": entry.model_dump_json(exclude={"id"})},
                    maxlen=LIVE_LOG_CAP,
                    approximate=True,
                )
            await pipe.execute()

    async def latest(self, limit: int) -> list[LiveLogEntry]:
        rows = await self._redis.xrevrange(LIVE_LOG_KEY, count=limit)
        return [self._entry(entry_id, fields) for entry_id, fields in reversed(rows)]

    async def after(self, cursor: str, *, limit: int, wait_seconds: float) -> list[LiveLogEntry]:
        streams = await self._redis.xread(
            {LIVE_LOG_KEY: cursor}, count=limit, block=max(1, int(wait_seconds * 1000))
        )
        return [
            self._entry(entry_id, fields) for _, rows in streams or [] for entry_id, fields in rows
        ]

    @staticmethod
    def _entry(entry_id: bytes | str, fields: dict) -> LiveLogEntry:
        raw = fields.get("entry") or fields.get(b"entry")
        text = raw.decode() if isinstance(raw, bytes) else raw
        identifier = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
        return LiveLogEntry.model_validate({**json.loads(text), "id": identifier})
