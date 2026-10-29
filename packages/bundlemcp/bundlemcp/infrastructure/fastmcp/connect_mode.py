"""Translating a server's protocol mode into the words the MCP client library uses."""

from fastmcp.client.client import ConnectMode

from bundlemcp.domain.servers.protocol_mode import NegotiationMode, ProtocolMode

# the client library's name for always using the initialize handshake
CLIENT_SESSION_MODE = "legacy"


def connect_mode(mode: ProtocolMode) -> ConnectMode:
    """The client's ``mode`` for a protocol mode: the session mode is the client's
    ``"legacy"``, ``auto`` stays ``"auto"``, and a pinned revision date is passed as is."""
    if mode == NegotiationMode.SESSION:
        return CLIENT_SESSION_MODE
    return str(mode)
