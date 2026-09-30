from pydantic import BaseModel, Field


class ProbedServerInfo(BaseModel):
    """How an upstream describes itself in its serverInfo."""

    name: str = Field(description="The implementation name the server reports")
    title: str | None = Field(default=None, description="Display title, when it sets one")
    description: str | None = Field(default=None, description="Description, when it sets one")
    version: str | None = Field(default=None, description="Implementation version")
    website_url: str | None = Field(default=None, description="Website, when it sets one")
