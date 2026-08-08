import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from bundlemcp.gateway.runtime_config._common import DEFAULTS, coerce
from bundlemcp.gateway.runtime_config.unknown_config_key import UnknownConfigKey
from bundlemcp.models import ConfigEntry

log = structlog.get_logger(__name__)


class RuntimeConfig:
    """Typed accessors with a per-replica cache invalidated via STP events."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory
        self._cache: dict[str, Any] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        if key not in DEFAULTS:
            raise UnknownConfigKey(key)
        if not self._loaded:
            await self._load()
        default, _typ = DEFAULTS[key]
        return self._cache.get(key, default)

    async def all(self) -> dict[str, Any]:
        if not self._loaded:
            await self._load()
        return {key: self._cache.get(key, default) for key, (default, _t) in DEFAULTS.items()}

    async def flush(self) -> None:
        """Drop the cache (invalidation event or subscription gap)."""
        async with self._lock:
            self._cache.clear()
            self._loaded = False

    async def _load(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            async with self._sessions() as db:
                rows = (await db.execute(select(ConfigEntry))).scalars().all()
            cache: dict[str, Any] = {}
            for row in rows:
                if row.key not in DEFAULTS:
                    continue  # stale/unknown keys are ignored, not fatal
                try:
                    cache[row.key] = coerce(row.key, row.value)
                except ValueError:
                    log.warning("runtime_config.invalid_value", key=row.key)
            self._cache = cache
            self._loaded = True
