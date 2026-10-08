from enum import StrEnum


class ProtocolEra(StrEnum):
    """The two families of MCP revisions the edge serves.

    Session-era clients open with ``initialize`` and hold a session in Valkey;
    stateless-era clients carry their version and capabilities on every request.
    """

    STATELESS = "stateless"
    SESSION = "session"
