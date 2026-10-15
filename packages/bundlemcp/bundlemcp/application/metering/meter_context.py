import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile

# Bytes the scratch mapping may take as JSON; it travels in every post-call
# event and in the record of a paused invocation.
SCRATCH_LIMIT_BYTES = 4096


def scratch_size(scratch: dict[str, Any]) -> int:
    """How many bytes ``scratch`` takes as compact JSON."""
    return len(json.dumps(scratch, separators=(",", ":"), default=str).encode())


class MeterContext(BaseModel):
    """What the metering hook is told about a single tool call."""

    model_config = ConfigDict(frozen=True)

    sub: str | None = Field(
        description="Caller identity: a user id, 'api_key:<id>', or None when anonymous"
    )
    email: str | None = Field(description="Caller email when the identity provider supplied one")
    oidc_issuer: str | None = Field(
        description="Identity provider that authenticated the caller; None for an API key "
        "or an anonymous caller"
    )
    oidc_sub: str | None = Field(
        description="The caller's subject at that identity provider, stable across logins and "
        "independent of this gateway's database; None for an API key or an anonymous caller"
    )
    auth_method: EndpointAuthMode = Field(
        description="How the caller authenticated: 'oauth', 'api_key' or 'none'"
    )
    endpoint: str = Field(description="Endpoint the call arrived on")
    profile: EndpointProfile = Field(
        description="The endpoint's profile, e.g. 'default' or 'write_as_read'"
    )
    bundle: str = Field(description="Bundle the endpoint exposes")
    session_id: str | None = Field(
        description="MCP session of a handshake-era client; None for a modern-era request, "
        "which has no session"
    )
    server: str = Field(description="Upstream server the call is routed to")
    tool: str = Field(description="Upstream tool name, without the bundle prefix")
    idempotency_key: str = Field(
        description="Stable key for one client invocation; internal retries reuse it, "
        "so the hook can charge exactly once",
    )
    headers: dict[str, str] = Field(
        description="The client's request headers, names lower-cased, without the ones that "
        "carry a credential (authorization, proxy-authorization, cookie, x-api-key). Read-only"
    )
    scratch: dict[str, Any] = Field(
        default_factory=dict,
        description="Data pre_call leaves for post_call, such as a reservation id: post_call "
        f"receives it as pre_call left it. At most {SCRATCH_LIMIT_BYTES} bytes as JSON",
    )
