"""Management-API DTOs: Pydantic models enforcing the domain rules that table
models can't (name patterns, endpoint auth modes, the profile/auth matrix).

One class per module, grouped by resource; everything re-exported here so
consumers keep importing from ``bundlemcp.schemas``.
"""

from bundlemcp.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from bundlemcp.schemas.audit import AuditRecordRead
from bundlemcp.schemas.bundles import (
    BundleMemberRead,
    BundleMembershipRead,
    BundleRead,
    BundleServerUpdate,
    BundleToolRead,
    BundleUpsert,
    ToolCurationRead,
)
from bundlemcp.schemas.common import EntityRead, Page
from bundlemcp.schemas.config import ConfigEntryRead, ConfigValue
from bundlemcp.schemas.endpoints import (
    EndpointProfileRead,
    EndpointRead,
    EndpointUpsert,
    RateLimitConfig,
    RateRule,
)
from bundlemcp.schemas.oauth import (
    AuthorizationServerMetadata,
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    IntrospectionResponse,
    ProtectedResourceMetadata,
    RevocationResponse,
    TokenResponse,
)
from bundlemcp.schemas.servers import (
    DiscoveryResult,
    ServerRead,
    ServerUpsert,
    UpstreamConnectionStatus,
    UpstreamOAuthClientRead,
    UpstreamOAuthConfig,
    UpstreamOAuthStatusRead,
)
from bundlemcp.schemas.tools import BundleToolUpdate, ToolRead
from bundlemcp.schemas.users import ConsentRead, MeRead, UserRead

__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyRead",
    "AuditRecordRead",
    "AuthorizationServerMetadata",
    "BundleMemberRead",
    "BundleMembershipRead",
    "BundleRead",
    "BundleServerUpdate",
    "BundleToolRead",
    "BundleToolUpdate",
    "BundleUpsert",
    "ClientRegistrationRequest",
    "ClientRegistrationResponse",
    "ConfigEntryRead",
    "ConfigValue",
    "ConsentRead",
    "DiscoveryResult",
    "EndpointProfileRead",
    "EndpointRead",
    "EndpointUpsert",
    "EntityRead",
    "IntrospectionResponse",
    "MeRead",
    "Page",
    "ProtectedResourceMetadata",
    "RateLimitConfig",
    "RateRule",
    "RevocationResponse",
    "ServerRead",
    "ServerUpsert",
    "TokenResponse",
    "ToolCurationRead",
    "ToolRead",
    "UpstreamConnectionStatus",
    "UpstreamOAuthClientRead",
    "UpstreamOAuthConfig",
    "UpstreamOAuthStatusRead",
    "UserRead",
]
