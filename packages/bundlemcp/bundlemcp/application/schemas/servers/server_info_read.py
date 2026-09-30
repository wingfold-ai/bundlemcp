from pydantic import BaseModel, Field


class ServerInfoRead(BaseModel):
    """How an upstream describes itself (its MCP serverInfo)."""

    name: str = Field(description="Implementation name the server reports")
    title: str | None = Field(default=None, description="Display title, when the server sets one")
    description: str | None = Field(
        default=None, description="What the server says it provides, when it says"
    )
    version: str | None = Field(default=None, description="Implementation version")
    website_url: str | None = Field(default=None, description="Website, when the server sets one")
