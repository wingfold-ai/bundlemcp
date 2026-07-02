"""Public URL derivation (DEP-1): every externally visible OAuth URL comes from
BUNDLEMCP_PUBLIC_URL — never from incoming Host headers.
"""

from bundlemcp.settings import Settings


def issuer(settings: Settings) -> str:
    return str(settings.public_url).rstrip("/")


def endpoint_resource(settings: Settings, endpoint_name: str) -> str:
    """Canonical resource identifier of an endpoint (OAS-10 / RFC 8707)."""
    return f"{issuer(settings)}/{endpoint_name}/mcp"


def endpoint_name_from_resource(settings: Settings, resource: str) -> str | None:
    """Reverse of endpoint_resource; None if the value isn't one of ours."""
    base = issuer(settings) + "/"
    if not resource.startswith(base) or not resource.endswith("/mcp"):
        return None
    name = resource[len(base) : -len("/mcp")]
    return name or None
