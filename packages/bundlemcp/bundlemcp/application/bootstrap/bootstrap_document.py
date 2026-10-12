from typing import Any

from pydantic import BaseModel, Field, model_validator

from bundlemcp.application.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.application.bootstrap.bootstrap_server import BootstrapServer
from bundlemcp.application.bootstrap.servers_key_rename import accept_former_key
from bundlemcp.application.schemas import EndpointUpsert


class BootstrapDocument(BaseModel):
    """A declarative snapshot applied at startup; applying it twice changes nothing."""

    version: int = Field(  # EXP-1: the export format this document follows
        default=1,
        ge=1,
        le=1,
        description="Format version of the document. Only 1 exists; a future format bumps it "
        "so an old document is rejected with a clear error rather than misread",
    )
    upstreams: list[BootstrapServer] = Field(  # BOOT-8
        default=[],
        description="Upstream servers to register or update, each optionally with the OAuth "
        "client the gateway presents to it. The former key 'servers' is still accepted",
    )
    bundles: list[BootstrapBundle] = Field(
        default=[], description="Bundles to create or update, with their membership"
    )
    endpoints: list[EndpointUpsert] = Field(default=[], description="Endpoints to create or update")

    @model_validator(mode="before")
    @classmethod
    def _accept_former_key(cls, data: Any) -> Any:
        return accept_former_key(data)
