from enum import StrEnum
from typing import Final, Literal


class ApiKeyScope(StrEnum):
    """What a scoped service key may do; a service key without scopes may do everything.

    Each management route declares the one scope it needs, or ``FULL`` (ADR-0066).
    """

    INTROSPECT = "introspect"  # POST /oauth/introspect
    READ = "read"  # reading the configuration: bundles, endpoints, upstreams, keys, settings
    BUNDLES_WRITE = "bundles:write"  # bundles, members, curation, bundle prompts and resources
    ENDPOINTS_WRITE = "endpoints:write"  # endpoints
    UPSTREAMS_WRITE = "upstreams:write"  # upstream servers, their discovery and upstream OAuth
    KEYS_MANAGE = "keys:manage"  # API keys, never beyond the caller's own scopes
    MCP = "mcp"  # calling tools on MCP endpoints that accept API keys


# A route only an admin session or an unscoped service key may call.
FULL: Final = "full"

RouteAccess = ApiKeyScope | Literal["full"]
