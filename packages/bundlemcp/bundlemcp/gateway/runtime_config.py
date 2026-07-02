"""Runtime-tunable configuration (spec 02 Config): ConfigEntry over typed defaults.

Values are cached per replica; the cache participates in STP invalidation
(entity_type="config"), so a PUT on any replica takes effect everywhere within
the STP-3 budget — never TTL-based (STP-4/STP-6).
"""

import asyncio
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from bundlemcp.models import ConfigEntry

log = structlog.get_logger(__name__)

# key -> (default, type). The single registry of runtime-tunable settings.
DEFAULTS: dict[str, tuple[Any, type]] = {
    # PROT-2 timeout model (seconds)
    "call_timeout": (60.0, float),
    "reset_timeout_on_progress": (True, bool),
    "max_total_timeout": (1800.0, float),
    # SES-10 (seconds; 0 = no idle expiry)
    "session_lifetime": (86400, int),
    # SRV-4
    "server_error_attempts": (3, int),
    # AUD-5 (days)
    "audit_retention_days": (90, int),
}


class UnknownConfigKey(KeyError):
    pass


def coerce(key: str, value: Any) -> Any:
    """Validate/coerce a raw (JSON) value against the key's registered type."""
    if key not in DEFAULTS:
        raise UnknownConfigKey(key)
    default, typ = DEFAULTS[key]
    if typ is bool:
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} must be a boolean")
    if typ is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{key} must be a number")
        return float(value)
    if typ is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        return value
    return value


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
        """STP-2: drop the cache (invalidation event or subscription gap)."""
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
