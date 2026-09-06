"""Which redirect URIs an MCP client may register or declare."""

from urllib.parse import urlparse

from bundlemcp.services.errors import InvalidInputError


def check_redirect_uri(uri: str) -> None:
    """Accept https anywhere, or http on the loopback host for native and dev clients."""
    parsed = urlparse(uri)
    if parsed.scheme == "https" and parsed.hostname:
        return
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return
    raise InvalidInputError(f"invalid_redirect_uri: {uri}")
