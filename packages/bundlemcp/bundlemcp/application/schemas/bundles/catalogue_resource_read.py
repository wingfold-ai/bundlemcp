from pydantic import BaseModel, Field


class CatalogueResourceRead(BaseModel):
    """A document the bundle itself offers, for someone deciding whether to connect it."""

    name: str = Field(description="Resource name, with '/' separating folders")
    title: str | None = Field(description="Human-readable title, when the administrator set one")
    description: str | None = Field(
        description="What the document contains; absent when the administrator wrote none"
    )
