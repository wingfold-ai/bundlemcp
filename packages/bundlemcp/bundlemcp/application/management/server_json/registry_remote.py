from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.management.server_json.registry_header import RegistryHeader
from bundlemcp.application.management.server_json.valid_entries import valid_entries

STREAMABLE_HTTP = "streamable-http"


class RegistryRemote(BaseModel):
    """One way a registry server.json says the server can be reached over the network."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    type: str | None = Field(
        default=None, description="Transport the remote speaks, such as 'streamable-http'"
    )
    url: str | None = Field(
        default=None, description="Where the remote listens; may hold {placeholders}"
    )
    headers: Annotated[list[RegistryHeader], valid_entries(RegistryHeader)] = Field(
        default_factory=list, description="Headers the remote declares, in the document's order"
    )

    @property
    def is_usable(self) -> bool:
        """Whether the gateway can reach the server through this remote."""
        return self.type == STREAMABLE_HTTP and bool(self.url)
