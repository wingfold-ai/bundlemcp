"""Management-API DTOs: Pydantic models enforcing the domain rules that table
models can't (name patterns, endpoint auth modes, the profile/auth matrix).

One class per module, grouped by resource; everything re-exported here so
consumers keep importing from ``bundlemcp.api.schemas``.
"""

from bundlemcp.api.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from bundlemcp.api.schemas.bundles import BundleRead, BundleServerUpdate, BundleUpsert
from bundlemcp.api.schemas.common import Page
from bundlemcp.api.schemas.config import ConfigValue
from bundlemcp.api.schemas.endpoints import (
    EndpointRead,
    EndpointUpsert,
    RateLimitConfig,
    RateRule,
)
from bundlemcp.api.schemas.servers import ServerRead, ServerUpsert, UpstreamOAuthConfig
from bundlemcp.api.schemas.tools import BundleToolUpdate, ToolRead
from bundlemcp.api.schemas.users import ConsentRead, UserRead

__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyRead",
    "BundleRead",
    "BundleServerUpdate",
    "BundleToolUpdate",
    "BundleUpsert",
    "ConfigValue",
    "ConsentRead",
    "EndpointRead",
    "EndpointUpsert",
    "Page",
    "RateLimitConfig",
    "RateRule",
    "ServerRead",
    "ServerUpsert",
    "ToolRead",
    "UpstreamOAuthConfig",
    "UserRead",
]
