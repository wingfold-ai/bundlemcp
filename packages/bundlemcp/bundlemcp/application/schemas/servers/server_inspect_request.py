from pydantic import BaseModel, Field, field_validator


class ServerInspectRequest(BaseModel):
    """Body for POST /servers:inspect."""

    url: str = Field(description="Streamable HTTP URL of the upstream MCP server to inspect")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Credential headers to try, such as {'authorization': 'Bearer …'} or "
        "{'x-api-key': '…'}. Used for this probe only: never stored, logged or returned",
    )

    @field_validator("url")
    @classmethod
    def url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v
