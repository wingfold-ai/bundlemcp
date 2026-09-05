"""The revisions that open with ``initialize`` and keep a session (2025-03-26 to 2025-11-25)."""

from typing import Any

from mcp.types import METHOD_NOT_FOUND

from bundlemcp.gateway.dialect.cache_hint import CacheHint
from bundlemcp.gateway.dialect.era import Era
from bundlemcp.gateway.dialect.neutral_error import NeutralError

# PROT-16: resource-not-found kept its pre-2026 number for handshake clients.
RESOURCE_NOT_FOUND_HANDSHAKE = -32002

# Methods that exist only in the modern era (PROT-13, PROT-14, PROT-17).
MODERN_ONLY_METHODS = frozenset({"server/discover", "subscriptions/listen"})


class HandshakeDialect:
    """Byte-for-byte the wire shape the edge spoke before the modern era existed."""

    def __init__(self, version: str) -> None:
        self._version = version

    @property
    def version(self) -> str:
        return self._version

    @property
    def era(self) -> Era:
        return Era.HANDSHAKE

    def allows(self, method: str) -> bool:
        return method not in MODERN_ONLY_METHODS

    def shape_result(
        self, result: dict[str, Any], *, server_info: dict[str, Any], cache_hint: CacheHint | None
    ) -> dict[str, Any]:
        return result

    def error_code(self, error: NeutralError) -> int:
        if error is NeutralError.RESOURCE_NOT_FOUND:
            return RESOURCE_NOT_FOUND_HANDSHAKE
        return METHOD_NOT_FOUND

    def http_status(self, code: int) -> int:
        # JSON-RPC errors travel in a 200 body in the handshake era.
        return 200
