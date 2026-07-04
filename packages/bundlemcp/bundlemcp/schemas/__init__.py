"""Management-API DTOs: Pydantic models enforcing the domain rules that table
models can't (name patterns, endpoint auth modes, the profile/auth matrix).

One class per module, grouped by resource; everything re-exported here so
consumers keep importing from ``bundlemcp.schemas``.
"""

from bundlemcp.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from bundlemcp.schemas.bundles import BundleRead, BundleServerUpdate, BundleUpsert
from bundlemcp.schemas.common import Page
from bundlemcp.schemas.config import ConfigValue
from bundlemcp.schemas.endpoints import (
    EndpointRead,
    EndpointUpsert,
    RateLimitConfig,
    RateRule,
)
from bundlemcp.schemas.servers import ServerRead, ServerUpsert, UpstreamOAuthConfig
from bundlemcp.schemas.tools import BundleToolUpdate, ToolRead
from bundlemcp.schemas.users import ConsentRead, UserRead

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
