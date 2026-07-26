"""Management-API DTOs: Pydantic models enforcing the domain rules that table
models can't (name patterns, endpoint auth modes, the profile/auth matrix).

One class per module, grouped by resource; everything re-exported here so
consumers keep importing from ``bundlemcp.schemas``.
"""

from bundlemcp.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyRead
from bundlemcp.schemas.audit import AuditRecordRead
from bundlemcp.schemas.bundles import (
    BundleMemberRead,
    BundleRead,
    BundleServerUpdate,
    BundleToolRead,
    BundleUpsert,
)
from bundlemcp.schemas.common import Page
from bundlemcp.schemas.endpoints import EndpointRead, EndpointUpsert
from bundlemcp.schemas.servers import ServerRead, ServerUpsert
from bundlemcp.schemas.tools import BundleToolUpdate, ToolRead
from bundlemcp.schemas.users import ConsentRead, MeRead, UserRead

__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyRead",
    "AuditRecordRead",
    "BundleMemberRead",
    "BundleRead",
    "BundleServerUpdate",
    "BundleToolRead",
    "BundleToolUpdate",
    "BundleUpsert",
    "ConsentRead",
    "EndpointRead",
    "MeRead",
    "EndpointUpsert",
    "Page",
    "ServerRead",
    "ServerUpsert",
    "ToolRead",
    "UserRead",
]
