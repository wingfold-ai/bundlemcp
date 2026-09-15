"""Which JSON-RPC methods a client may send at one MCP revision, from the SDK's registry."""

from itertools import chain

from mcp_types.methods import CLIENT_NOTIFICATIONS, CLIENT_REQUESTS


def client_methods(version: str) -> frozenset[str]:
    """Every request and notification method the revision defines on the client-to-server path.

    The edge serves a method only if the revision defines it, so ``ping`` or
    ``initialize`` at a stateless revision, or ``server/discover`` at a
    handshake one, is "method not found" without a hand-kept denylist.
    """
    return frozenset(
        method for method, at in chain(CLIENT_REQUESTS, CLIENT_NOTIFICATIONS) if at == version
    )
