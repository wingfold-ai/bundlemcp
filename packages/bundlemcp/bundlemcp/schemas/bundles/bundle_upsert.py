from pydantic import BaseModel, Field

from bundlemcp.schemas.resource_names import ResourceName


class BundleUpsert(BaseModel):
    """Body for creating or replacing a bundle."""

    name: ResourceName = Field(
        description="Unique bundle name; lowercase letters, digits and hyphens"
    )
    description: str | None = Field(
        default=None, description="Free-text note about what this bundle is for"
    )
