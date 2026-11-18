"""Which MCP revisions the edge speaks, and which dialect serves each."""

from bundlemcp.api.mcp.protocol.dialect.handshake_dialect import HandshakeDialect
from bundlemcp.api.mcp.protocol.dialect.modern_dialect import ModernDialect
from bundlemcp.api.mcp.protocol.protocol_version import (
    HANDSHAKE_PROTOCOL_VERSIONS,
    MODERN_PROTOCOL_VERSIONS,
    negotiate_handshake_version,
)


class DialectRegistry:
    # one registration per revision, no other edit
    """The supported revisions, newest first within each era.

    Adding a revision means registering one more dialect here; the router, the
    handlers and the relay do not change.
    """

    def __init__(self, *, modern: list[ModernDialect], handshake: list[HandshakeDialect]) -> None:
        self._modern = {d.version: d for d in modern}
        self._handshake = {d.version: d for d in handshake}

    @classmethod
    def default(cls, *, legacy_enabled: bool) -> DialectRegistry:
        return cls(
            modern=[ModernDialect(v) for v in MODERN_PROTOCOL_VERSIONS],
            handshake=[HandshakeDialect(v) for v in HANDSHAKE_PROTOCOL_VERSIONS]
            if legacy_enabled
            else [],
        )

    @property
    def modern_versions(self) -> list[str]:
        return list(self._modern)

    @property
    def handshake_versions(self) -> list[str]:
        return list(self._handshake)

    def modern(self, version: str) -> ModernDialect | None:
        return self._modern.get(version)

    def negotiate_handshake(self, requested: str | None) -> HandshakeDialect | None:
        """The handshake dialect for a client's ``initialize``, or None if there is no overlap."""
        version = negotiate_handshake_version(requested, self.handshake_versions)
        return self._handshake.get(version) if version is not None else None

    def handshake(self, version: str) -> HandshakeDialect | None:
        """The dialect recorded on a session, or None if it is no longer served."""
        return self._handshake.get(version)
