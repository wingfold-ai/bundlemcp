from pydantic import BaseModel, Field


class BundleServerUpdate(BaseModel):
    """Body for toggling one server's membership in a bundle."""

    enabled: bool = Field(
        default=True,
        description="Whether the server's tools are served through this bundle",
    )
