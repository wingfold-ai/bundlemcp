from pydantic import BaseModel, Field

from bundlemcp.domain.shared.resource_names import ResourceName


class BundleUpsert(BaseModel):
    """Body for creating or replacing a bundle."""

    name: ResourceName = Field(
        description="Unique bundle name: letters, digits, underscores and hyphens"
    )
    description: str | None = Field(
        default=None, description="Free-text note about what this bundle is for"
    )
    overview: str | None = Field(
        default=None,
        description="Long-form description of the bundle for people browsing the "
        "catalogue: what it is for, what the tools can do, and anything a user must set "
        "up first. Plain text, paragraphs separated by blank lines. Unlike 'description' "
        "this is never sent to a model, so it can be as long as it needs to be",
    )
