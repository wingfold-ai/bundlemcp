import asyncio
from datetime import timedelta

import structlog

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.domain.config.call_timeouts import CallTimeouts
from bundlemcp.domain.config.config_registry import DEFAULTS, coerce
from bundlemcp.domain.config.runtime_settings import RuntimeSettings
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.sessions.session_lifetime import SessionLifetime

log = structlog.get_logger(__name__)


class RuntimeConfig:
    """Typed runtime settings with a per-replica cache invalidated via invalidation events.

    Besides the cache, a snapshot holds the settings of the last completed load.
    A flush does not clear it, so ``snapshot`` keeps answering with the stored
    values until the next load replaces them.

    With ``cache_disabled`` every ``settings()`` reads the store, a debugging aid
    that must change nothing but speed; ``snapshot`` still answers from the last
    read, since it must never do I/O.
    """

    def __init__(self, units: UnitOfWorkFactory, *, cache_disabled: bool = False) -> None:
        self._units = units
        self._cache_disabled = cache_disabled
        self._cache = RuntimeSettings()
        self._snapshot = RuntimeSettings()
        self._loaded = False
        self._lock = asyncio.Lock()

    async def settings(self) -> RuntimeSettings:
        """The settings in effect: stored overrides over the registry defaults."""
        if self._cache_disabled:
            await self.flush()
        if not self._loaded:
            await self._load()
        return self._cache

    @property
    def snapshot(self) -> RuntimeSettings:
        """The settings as of the last load, without any I/O.

        For checks that must not wait on the database, such as the request
        size limit that runs before a request is admitted. Before the first
        load it holds the registry defaults.
        """
        return self._snapshot

    async def session_lifetime(self) -> SessionLifetime:
        """How long a handshake-era session lives without activity."""
        return SessionLifetime(seconds=(await self.settings()).session_lifetime)

    async def call_timeouts(self) -> CallTimeouts:
        """The current upstream call limits, from overrides or the registry defaults."""
        settings = await self.settings()
        return CallTimeouts(
            call=settings.call_timeout,
            reset_on_progress=settings.reset_timeout_on_progress,
            max_total=settings.max_total_timeout,
        )

    async def token_policy(self) -> TokenPolicy:
        """The lifetimes the OAuth server issues with, from overrides or the defaults."""
        settings = await self.settings()
        return TokenPolicy(
            authorization_code_ttl=timedelta(seconds=settings.authorization_code_lifetime),
            access_token_ttl=timedelta(seconds=settings.access_token_lifetime),
            refresh_token_ttl=timedelta(seconds=settings.refresh_token_lifetime),
        )

    async def flush(self) -> None:
        """Drop the cache (invalidation event or subscription gap)."""
        async with self._lock:
            self._cache = RuntimeSettings()
            self._loaded = False

    async def refresh(self) -> None:
        """Drop the cache and load it again, so the snapshot follows a change promptly.

        A failed load is logged and leaves the snapshot as it was; the next
        ``settings()`` loads again.
        """
        await self.flush()
        try:
            await self._load()
        except Exception:
            log.warning("runtime_config.reload_failed", exc_info=True)

    async def _load(self) -> None:
        async with self._lock:
            if self._loaded:
                return
            async with self._units.open() as uow:
                rows = await uow.config_entries.all()
            overrides: dict[str, bool | int | float] = {}
            for row in rows:
                if row.key not in DEFAULTS:
                    continue  # stale/unknown keys are ignored, not fatal
                try:
                    overrides[row.key] = coerce(row.key, row.value)
                except ValueError:
                    log.warning("runtime_config.invalid_value", key=row.key)
            self._cache = RuntimeSettings(**overrides)
            self._snapshot = self._cache
            self._loaded = True
