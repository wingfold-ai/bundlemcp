"""The stateless revisions (2026-07-28 and later): per-request ``_meta``, decorated results."""

from typing import Any

from mcp.shared.inbound import ERROR_CODE_HTTP_STATUS
from mcp.types import INVALID_PARAMS, METHOD_NOT_FOUND, SERVER_INFO_META_KEY

from bundlemcp.api.mcp.protocol.dialect.cache_hint import CacheHint
from bundlemcp.api.mcp.protocol.dialect.client_methods import client_methods
from bundlemcp.api.mcp.protocol.dialect.era import ProtocolEra
from bundlemcp.api.mcp.protocol.dialect.neutral_error import NeutralError


class ModernDialect:
    """One stateless revision as seen by a client."""

    def __init__(self, version: str) -> None:
        self._version = version
        self._methods = client_methods(version)

    @property
    def version(self) -> str:
        return self._version

    @property
    def era(self) -> ProtocolEra:
        return ProtocolEra.STATELESS

    def allows(self, method: str) -> bool:
        return method in self._methods

    def shape_result(
        self, result: dict[str, Any], *, server_info: dict[str, Any], cache_hint: CacheHint | None
    ) -> dict[str, Any]:
        # PROT-16: resultType is required; the gateway names itself, not the
        # upstream that produced the payload.
        shaped = dict(result)
        shaped.setdefault("resultType", "complete")
        meta = dict(shaped.get("_meta") or {})
        meta[SERVER_INFO_META_KEY] = server_info
        shaped["_meta"] = meta
        if cache_hint is not None:
            shaped["ttlMs"] = cache_hint.ttl_ms
            shaped["cacheScope"] = cache_hint.scope
        return shaped

    def error_code(self, error: NeutralError) -> int:
        if error is NeutralError.RESOURCE_NOT_FOUND:
            return INVALID_PARAMS
        return METHOD_NOT_FOUND

    def http_status(self, code: int) -> int:
        return ERROR_CODE_HTTP_STATUS.get(code, 200)
