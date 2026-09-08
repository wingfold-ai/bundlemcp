from pydantic import BaseModel, Field


class BundleMembershipRead(BaseModel):
    """The result of adding a server to a bundle or toggling its membership."""

    bundle: str = Field(description="Bundle the server belongs to")
    server: str = Field(description="Member server")
    enabled: bool = Field(description="Whether the membership currently contributes tools")
