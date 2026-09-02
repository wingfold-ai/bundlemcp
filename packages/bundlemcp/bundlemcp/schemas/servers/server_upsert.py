from typing import Literal

from pydantic import BaseModel, Field, field_validator

from bundlemcp.models import ServerAuthMode
from bundlemcp.schemas.validation import validate_name


class ServerUpsert(BaseModel):
    """Body for POST /servers and PUT /servers/{name}."""

    name: str = Field(
        description="Unique server name; lowercase letters, digits and hyphens, and it may "
        "not contain a double underscore because that separates server from tool"
    )
    description: str | None = Field(
        default=None, description="Free-text note about what this server provides"
    )
    url: str = Field(description="Streamable HTTP URL of the upstream MCP server")
    static_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers sent on every upstream request, for credentials the server needs. "
        "Values are write-only and never returned",
    )
    forward_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Client headers to pass through, mapped from incoming name to upstream name",
    )
    auth_mode: ServerAuthMode = Field(
        default=ServerAuthMode.NONE,
        description="How the gateway authenticates to this server",
    )
    identity_mode: Literal["shared", "per_user"] = Field(
        default="shared",
        description="Whether all callers share one upstream identity or each gets their own",
    )
    send_identity_header: bool = Field(
        default=True,
        description="Whether the calling user's identity is forwarded to the upstream server",
    )
    transport: Literal["streamable-http"] | None = Field(  # API-4
        default=None,
        description="Upstream transport. Only streamable-http is supported; the field exists "
        "so payloads that state it explicitly are accepted",
    )
    force: bool = Field(  # SRV-5
        default=False,
        description="Confirm a rename that would otherwise be rejected, accepting that bundles "
        "and tool names derived from the old name change with it",
    )

    @field_validator("name")
    @classmethod
    def name_rules(cls, v: str) -> str:
        validate_name(v)
        if "__" in v:
            raise ValueError("server names must not contain '__' (DOM-4/BND-2)")
        return v

    @field_validator("url")
    @classmethod
    def url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v
