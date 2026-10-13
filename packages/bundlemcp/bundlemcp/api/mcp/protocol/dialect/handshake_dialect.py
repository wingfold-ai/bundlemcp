"""The revisions that open with ``initialize`` and keep a session (2025-03-26 to 2025-11-25)."""

from typing import Any

from mcp.types import METHOD_NOT_FOUND

from bundlemcp.api.mcp.protocol.dialect.cache_hint import CacheHint
from bundlemcp.api.mcp.protocol.dialect.client_methods import client_methods
from bundlemcp.api.mcp.protocol.dialect.era import ProtocolEra
from bundlemcp.api.mcp.protocol.dialect.neutral_error import NeutralError

# resource-not-found kept its pre-2026 number for handshake clients.
RESOURCE_NOT_FOUND_HANDSHAKE = -32002


class HandshakeDialect:
    """Byte-for-byte the wire shape the edge spoke before the modern era existed."""

    def __init__(self, version: str) -> None:
        self._version = version
        self._methods = client_methods(version)

    @property
    def version(self) -> str:
        return self._version

    @property
    def era(self) -> ProtocolEra:
        return ProtocolEra.SESSION

    def allows(self, method: str) -> bool:
        return method in self._methods

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
