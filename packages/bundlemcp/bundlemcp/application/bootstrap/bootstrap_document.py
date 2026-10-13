from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.application.bootstrap.bootstrap_server import BootstrapServer
from bundlemcp.application.schemas import EndpointUpsert


class BootstrapDocument(BaseModel):
    """A declarative snapshot applied at startup; applying it twice changes nothing.

    An unknown key is an error rather than ignored, so a misspelt or outdated
    list name fails loudly instead of quietly provisioning nothing.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(  # the export format this document follows
        default=1,
        ge=1,
        le=1,
        description="Format version of the document. Only 1 exists; a future format bumps it "
        "so an old document is rejected with a clear error rather than misread",
    )
    upstreams: list[BootstrapServer] = Field(
        default=[],
        description="Upstream servers to register or update, each optionally with the OAuth "
        "client the gateway presents to it",
    )
    bundles: list[BootstrapBundle] = Field(
        default=[], description="Bundles to create or update, with their membership"
    )
    endpoints: list[EndpointUpsert] = Field(default=[], description="Endpoints to create or update")
