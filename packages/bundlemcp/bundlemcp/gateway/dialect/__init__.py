"""One dialect per MCP revision: what differs on the wire to the client, and nothing else."""

from bundlemcp.gateway.dialect.cache_hint import CacheHint
from bundlemcp.gateway.dialect.dialect_registry import DialectRegistry
from bundlemcp.gateway.dialect.era import Era
from bundlemcp.gateway.dialect.handshake_dialect import HandshakeDialect
from bundlemcp.gateway.dialect.modern_dialect import ModernDialect
from bundlemcp.gateway.dialect.neutral_error import NeutralError
from bundlemcp.gateway.dialect.wire_dialect import WireDialect

__all__ = [
    "CacheHint",
    "DialectRegistry",
    "Era",
    "HandshakeDialect",
    "ModernDialect",
    "NeutralError",
    "WireDialect",
]
