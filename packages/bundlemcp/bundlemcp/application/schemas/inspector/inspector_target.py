from typing import Annotated, Literal

from pydantic import BaseModel, Field


class UpstreamInspectorTarget(BaseModel):
    """A registered upstream server, reached with its stored configuration."""

    kind: Literal["upstream"] = Field(description="Selects this target kind")
    name: str = Field(min_length=1, description="Name of the registered upstream server")


class EndpointInspectorTarget(BaseModel):
    """An endpoint of this gateway, reached through its public MCP route."""

    kind: Literal["endpoint"] = Field(description="Selects this target kind")
    name: str = Field(min_length=1, description="Name of the endpoint")
    credential: str | None = Field(
        default=None,
        description="What a client of the endpoint would present: an API key scoped to it, or "
        "an OAuth access token issued for it. Sent as a bearer token for this request only, "
        "never stored or logged. Omit it for an endpoint that accepts anonymous calls",
    )


class AdhocInspectorTarget(BaseModel):
    """A URL that is not registered, with the headers to send to it."""

    kind: Literal["adhoc"] = Field(description="Selects this target kind")
    url: str = Field(
        pattern=r"^https?://",
        max_length=2048,
        description="Streamable HTTP MCP endpoint URL, e.g. 'https://mcp.example.com/mcp'. It "
        "must pass the gateway's egress policy",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers sent with every request of this operation, e.g. an "
        "'Authorization' header. Used once, never stored or logged",
    )


InspectorTarget = Annotated[
    UpstreamInspectorTarget | EndpointInspectorTarget | AdhocInspectorTarget,
    Field(discriminator="kind"),
]
