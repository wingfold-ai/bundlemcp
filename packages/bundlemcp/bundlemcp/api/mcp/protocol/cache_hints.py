"""The cache hints the gateway can honestly give."""

# how long a client may keep a tools/prompts/resources list.

from typing import Any

from bundlemcp.api.mcp.protocol.dialect import CacheHint
from bundlemcp.application.serving.runtime_config import RuntimeConfig

NO_CACHE_PRIVATE = CacheHint(ttl_ms=0, scope="private")


class CacheHints:
    """List results are the same for every caller of an endpoint; reads may not be, except
    of a resource the bundle itself serves."""

    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self._runtime_config = runtime_config

    async def for_list(self) -> CacheHint:
        ttl_ms = await self._runtime_config.get("list_cache_ttl_ms")
        return CacheHint(ttl_ms=int(ttl_ms), scope="public")

    async def for_bundle_resource(self) -> CacheHint:
        """A bundle's own resource reads the same for every caller, so it caches like a list."""
        return await self.for_list()

    @staticmethod
    def for_read(upstream_result: dict[str, Any]) -> CacheHint:
        """Forward the upstream's own hint when it gave one; otherwise never cache."""
        ttl_ms = upstream_result.get("ttlMs")
        scope = upstream_result.get("cacheScope")
        if isinstance(ttl_ms, int) and ttl_ms >= 0 and scope in ("public", "private"):
            return CacheHint(ttl_ms=ttl_ms, scope=scope)
        return NO_CACHE_PRIVATE
