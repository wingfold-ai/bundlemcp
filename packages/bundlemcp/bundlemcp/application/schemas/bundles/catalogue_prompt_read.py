from pydantic import BaseModel, Field


class CataloguePromptRead(BaseModel):
    """A prompt the bundle itself offers, for someone deciding whether to connect it."""

    name: str = Field(description="Name the client lists the prompt under")
    title: str | None = Field(description="Human-readable title, when the administrator set one")
    description: str | None = Field(
        description="What the prompt is for; absent when the administrator wrote none"
    )
