from enum import StrEnum


class Era(StrEnum):
    """The two families of MCP revisions the edge serves.

    Handshake-era clients open with ``initialize`` and hold a session; modern-era
    clients carry their version and capabilities on every request.
    """

    HANDSHAKE = "handshake"
    MODERN = "modern"
