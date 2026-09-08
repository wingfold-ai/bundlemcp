from typing import Any, Protocol, runtime_checkable

from bundlemcp.api.mcp.dialect.cache_hint import CacheHint
from bundlemcp.api.mcp.dialect.era import Era
from bundlemcp.api.mcp.dialect.neutral_error import NeutralError


@runtime_checkable
class WireDialect(Protocol):
    """Everything about one MCP revision that differs on the wire to the client.

    A dialect is selected once per request from how the client opened, and it is
    the only place the edge consults for revision-specific shape: which methods
    exist, how a result is decorated, which error number a condition maps to,
    and which HTTP status accompanies a JSON-RPC error.
    """

    @property
    def version(self) -> str: ...

    @property
    def era(self) -> Era: ...

    def allows(self, method: str) -> bool:
        """Whether the revision defines this JSON-RPC method on the client-to-server path."""
        ...

    def shape_result(
        self, result: dict[str, Any], *, server_info: dict[str, Any], cache_hint: CacheHint | None
    ) -> dict[str, Any]:
        """Decorate a version-neutral result the way this revision expects."""
        ...

    def error_code(self, error: NeutralError) -> int: ...

    def http_status(self, code: int) -> int:
        """HTTP status that accompanies a JSON-RPC error with this code."""
        ...
