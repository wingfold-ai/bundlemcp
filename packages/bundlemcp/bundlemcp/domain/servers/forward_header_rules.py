"""Which client headers may ever be forwarded to an upstream server."""

# Never forwarded regardless of a server's mapping.
DENIED_FORWARD_HEADERS = frozenset(
    {"host", "content-length", "cookie", "x-api-key", "mcp-session-id"}
)
DENIED_FORWARD_PREFIXES = ("sec-", "proxy-")
CALLER_TOKEN_HEADER = "authorization"  # noqa: S105


def is_forwardable(header: str) -> bool:
    """Whether a header name may appear in a forward mapping at all."""
    lower = header.lower()
    return lower not in DENIED_FORWARD_HEADERS and not lower.startswith(DENIED_FORWARD_PREFIXES)
