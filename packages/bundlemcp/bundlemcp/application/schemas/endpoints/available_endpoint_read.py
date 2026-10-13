from pydantic import BaseModel, Field

from bundlemcp.domain.endpoints.endpoint_profile import EndpointProfile


class AvailableEndpointRead(BaseModel):
    """An endpoint a signed-in person can connect an MCP client to with their own identity."""

    name: str = Field(description="Endpoint name, the last path segment before /mcp")
    url: str = Field(
        description="Full Streamable HTTP URL to enter in the MCP client, such as claude.ai's "
        "custom connector dialog"
    )
    profile: EndpointProfile = Field(
        description="Client the endpoint is shaped for: default for any MCP client, claude for "
        "claude.ai, chatgpt for ChatGPT"
    )
    bundle_name: str = Field(description="Bundle the endpoint serves")
    bundle_description: str | None = Field(
        description="What the bundle offers, as its administrator described it"
    )
    bundle_overview: str | None = Field(
        description="The administrator's long-form description of the bundle, for the "
        "catalogue page; absent when none was written"
    )
