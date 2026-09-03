"""Which client headers cross to an upstream, and the identity the gateway adds."""

from collections.abc import Mapping

from bundlemcp.models import McpServer

# Never forwarded regardless of a server's mapping (DOM-3 / SEC-3).
DENIED_FORWARD_HEADERS = {"host", "content-length", "cookie", "x-api-key", "mcp-session-id"}
IDENTITY_HEADER = "X-MCP-User"  # spec 24


def forwarded_headers(
    client_headers: Mapping[str, str], server: McpServer, sub: str | None
) -> dict[str, str]:
    """Build the extra headers forwarded upstream.

    Applies the server's configured header mappings, skipping denied headers,
    then injects the gateway's own identity header (any client-supplied
    identity header is always stripped).
    """
    extra: dict[str, str] = {}
    for client_header, upstream_header in server.forward_headers.items():
        lower = client_header.lower()
        if lower in DENIED_FORWARD_HEADERS or lower.startswith(("sec-", "proxy-")):
            continue
        value = client_headers.get(client_header)
        if value is not None:
            extra[upstream_header] = value
    # client-supplied identity header is always stripped; gateway injects its own
    extra.pop(IDENTITY_HEADER, None)
    if server.send_identity_header and sub is not None:
        extra[IDENTITY_HEADER] = sub
    return extra
