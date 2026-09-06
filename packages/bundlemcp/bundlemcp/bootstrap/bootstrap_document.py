from pydantic import BaseModel, Field

from bundlemcp.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.schemas import EndpointUpsert, ServerUpsert


class BootstrapDocument(BaseModel):
    """A declarative snapshot applied at startup; applying it twice changes nothing."""

    servers: list[ServerUpsert] = Field(
        default=[], description="Upstream servers to register or update"
    )
    bundles: list[BootstrapBundle] = Field(
        default=[], description="Bundles to create or update, with their membership"
    )
    endpoints: list[EndpointUpsert] = Field(default=[], description="Endpoints to create or update")
