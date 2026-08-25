from pydantic import BaseModel

from bundlemcp.bootstrap.bootstrap_bundle import BootstrapBundle
from bundlemcp.bootstrap.bootstrap_server import BootstrapServer
from bundlemcp.schemas import EndpointUpsert


class BootstrapDocument(BaseModel):
    servers: list[BootstrapServer] = []
    bundles: list[BootstrapBundle] = []
    endpoints: list[EndpointUpsert] = []
