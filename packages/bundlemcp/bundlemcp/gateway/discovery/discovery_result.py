from pydantic import BaseModel, Field


class DiscoveryResult(BaseModel):
    """Outcome of one probe against an upstream server."""

    discovered: int = Field(default=0, description="Tools the upstream reported in this probe")
    changed: int = Field(
        default=0,
        description="Tools written to the cache because their definition hash moved",
    )
    error: str | None = Field(
        default=None,
        description="Why the probe failed; None when it succeeded",
    )
