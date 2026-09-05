"""The cache hints the gateway can honestly give (PROT-16)."""

from typing import Any

from bundlemcp.gateway.dialect import CacheHint
from bundlemcp.gateway.runtime_config import RuntimeConfig

NO_CACHE_PRIVATE = CacheHint(ttl_ms=0, scope="private")


class CacheHints:
    """List results are the same for every caller of an endpoint; reads may not be."""

    def __init__(self, runtime_config: RuntimeConfig) -> None:
        self._runtime_config = runtime_config

    async def for_list(self) -> CacheHint:
        ttl_ms = await self._runtime_config.get("list_cache_ttl_ms")
        return CacheHint(ttl_ms=int(ttl_ms), scope="public")

    @staticmethod
    def for_read(upstream_result: dict[str, Any]) -> CacheHint:
        """Forward the upstream's own hint when it gave one; otherwise never cache."""
        ttl_ms = upstream_result.get("ttlMs")
        scope = upstream_result.get("cacheScope")
        if isinstance(ttl_ms, int) and ttl_ms >= 0 and scope in ("public", "private"):
            return CacheHint(ttl_ms=ttl_ms, scope=scope)
        return NO_CACHE_PRIVATE
