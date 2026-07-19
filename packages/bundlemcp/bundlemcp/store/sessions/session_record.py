from typing import Any

from pydantic import BaseModel, Field

from bundlemcp.store.sessions._common import SESSION_RECORD_VERSION
from bundlemcp.store.sessions.upstream_binding import UpstreamBinding


class SessionRecord(BaseModel):
    version: int = SESSION_RECORD_VERSION
    session_id: str
    endpoint_name: str
    bundle_name: str
    auth_method: str  # oauth | api_key | none
    user_id: str | None = None
    user_email: str | None = None  # feeds MeterContext.email (MID-3)
    api_key_id: str | None = None
    protocol_version: str
    client_capabilities: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, UpstreamBinding] = Field(default_factory=dict)  # by server name
