from pydantic import BaseModel, Field

from bundlemcp.application.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.application.schemas import EndpointUpsert, ServerUpsert


class BootstrapDocument(BaseModel):
    """A declarative snapshot applied at startup; applying it twice changes nothing."""

    version: int = Field(  # EXP-1: the export format this document follows
        default=1,
        ge=1,
        le=1,
        description="Format version of the document. Only 1 exists; a future format bumps it "
        "so an old document is rejected with a clear error rather than misread",
    )
    servers: list[ServerUpsert] = Field(
        default=[], description="Upstream servers to register or update"
    )
    bundles: list[BootstrapBundle] = Field(
        default=[], description="Bundles to create or update, with their membership"
    )
    endpoints: list[EndpointUpsert] = Field(default=[], description="Endpoints to create or update")
