from pydantic import BaseModel, Field


class MemberEntryCurationUpdate(BaseModel):
    """How a bundle presents one member prompt or resource; the whole curation is replaced."""

    enabled: bool = Field(
        default=True,
        description="Whether the bundle lists and serves it; false hides it from clients of this "
        "bundle and refuses fetching it",
    )
    override_title: str | None = Field(
        default=None, description="Title presented instead of the upstream's; null keeps it"
    )
    override_description: str | None = Field(
        default=None,
        description="Description presented instead of the upstream's; null keeps it",
    )
