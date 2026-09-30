from pydantic import BaseModel, Field


class DiscoverySweep(BaseModel):
    """Outcome of re-running discovery for every registered server in one pass."""

    servers: int = Field(default=0, description="Servers probed in this pass")
    failed: int = Field(
        default=0,
        description="Servers whose probe failed; their cached tools stay as they were",
    )
    changed: int = Field(
        default=0,
        description="Tools written to the cache across all servers because their definition "
        "hash moved",
    )
