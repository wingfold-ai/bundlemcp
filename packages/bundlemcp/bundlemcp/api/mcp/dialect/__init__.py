"""One dialect per MCP revision: what differs on the wire to the client, and nothing else."""

from bundlemcp.api.mcp.dialect.cache_hint import CacheHint
from bundlemcp.api.mcp.dialect.dialect_registry import DialectRegistry
from bundlemcp.api.mcp.dialect.era import Era
from bundlemcp.api.mcp.dialect.handshake_dialect import HandshakeDialect
from bundlemcp.api.mcp.dialect.modern_dialect import ModernDialect
from bundlemcp.api.mcp.dialect.neutral_error import NeutralError
from bundlemcp.api.mcp.dialect.wire_dialect import WireDialect

__all__ = [
    "CacheHint",
    "DialectRegistry",
    "Era",
    "HandshakeDialect",
    "ModernDialect",
    "NeutralError",
    "WireDialect",
]
