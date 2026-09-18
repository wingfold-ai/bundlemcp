import asyncio
from datetime import timedelta
from typing import Any

import structlog

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.domain.config.call_timeouts import CallTimeouts
from bundlemcp.domain.config.config_registry import DEFAULTS, coerce
from bundlemcp.domain.config.unknown_config_key import UnknownConfigKey
from bundlemcp.domain.oauth.token_policy import TokenPolicy

log = structlog.get_logger(__name__)


class RuntimeConfig:
    """Typed accessors with a per-replica cache invalidated via STP events."""

    def __init__(self, units: UnitOfWorkFactory) -> None:
        self._units = units
        self._cache: dict[str, Any] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        if key not in DEFAULTS:
            raise UnknownConfigKey(key)
        if not self._loaded:
            await self._load()
        return self._cache.get(key, DEFAULTS[key].default)

    async def call_timeouts(self) -> CallTimeouts:
        """The current upstream call limits, from overrides or the registry defaults."""
        return CallTimeouts(
            call=float(await self.get("call_timeout")),
            reset_on_progress=bool(await self.get("reset_timeout_on_progress")),
            max_total=float(await self.get("max_total_timeout")),
        )

    async def token_policy(self) -> TokenPolicy:
        """The lifetimes the OAuth server issues with, from overrides or the defaults."""
        return TokenPolicy(
            authorization_code_ttl=timedelta(
                seconds=int(await self.get("authorization_code_lifetime"))
            ),
            access_token_ttl=timedelta(seconds=int(await self.get("access_token_lifetime"))),
            refresh_token_ttl=timedelta(seconds=int(await self.get("refresh_token_lifetime"))),
        )

    async def all(self) -> dict[str, Any]:
        if not self._loaded:
            await self._load()
        return {key: self._cache.get(key, setting.default) for key, setting in DEFAULTS.items()}

    async def flush(self) -> None:
        """Drop the cache (invalidation event or subscription gap)."""
        async with self._lock:
            self._cache.clear()
            self._loaded = False

    async def _load(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            async with self._units.open() as uow:
                rows = await uow.config_entries.all()
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
