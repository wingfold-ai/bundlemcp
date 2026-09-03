"""Public URL derivation: every externally visible OAuth URL comes from
BUNDLEMCP_PUBLIC_URL — never from incoming Host headers.
"""

from bundlemcp.settings import Settings


def endpoint_resource(settings: Settings, endpoint_name: str) -> str:
    """Canonical resource identifier of an endpoint (RFC 8707)."""
    return f"{settings.public_base}/{endpoint_name}/mcp"
