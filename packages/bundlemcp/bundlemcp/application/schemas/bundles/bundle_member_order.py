from pydantic import BaseModel, Field

from bundlemcp.domain.shared.resource_names import ResourceName


class BundleMemberOrder(BaseModel):
    """Body for setting the order of a bundle's member upstreams."""

    upstreams: list[ResourceName] = Field(
        description="Every member upstream of the bundle, each exactly once, first member "
        "first. The first member in this order answers first wherever more than one could, "
        "such as a resource URI two members both list"
    )
