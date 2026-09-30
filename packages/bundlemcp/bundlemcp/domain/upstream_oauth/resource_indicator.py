"""The RFC 8707 resource an upstream token is requested for."""

from typing import Any
from urllib.parse import urlparse


def canonical_resource(server_url: str) -> str:
    """The server URL as a resource: lower-case origin, no fragment or trailing slash."""
    parsed = urlparse(server_url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def resource_indicator(server_url: str, document: dict[str, Any] | None) -> str:
    """The protected resource's own identifier when it covers the server, else the URL.

    A resource document may name a parent of the server URL (one identifier
    for several MCP paths); anything else it names is ignored rather than
    requested, so a token is never asked for a resource the server is not.
    """
    canonical = canonical_resource(server_url)
    named = (document or {}).get("resource")
    if isinstance(named, str) and named:
        candidate = canonical_resource(named)
        if canonical == candidate or canonical.startswith(candidate + "/"):
            return named
    return canonical
