"""One dialect per MCP revision: what differs on the wire to the client, and nothing else."""

from bundlemcp.api.mcp.protocol.dialect.cache_hint import CacheHint
from bundlemcp.api.mcp.protocol.dialect.dialect_registry import DialectRegistry
from bundlemcp.api.mcp.protocol.dialect.era import Era, ProtocolEra
from bundlemcp.api.mcp.protocol.dialect.handshake_dialect import HandshakeDialect
from bundlemcp.api.mcp.protocol.dialect.modern_dialect import ModernDialect
from bundlemcp.api.mcp.protocol.dialect.neutral_error import NeutralError
from bundlemcp.api.mcp.protocol.dialect.wire_dialect import WireDialect

__all__ = [
    "CacheHint",
    "DialectRegistry",
    "Era",
    "HandshakeDialect",
    "ModernDialect",
    "NeutralError",
    "ProtocolEra",
    "WireDialect",
]
