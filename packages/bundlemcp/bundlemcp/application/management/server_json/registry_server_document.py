from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.application.management.server_json.registry_remote import RegistryRemote
from bundlemcp.application.management.server_json.valid_entries import valid_entries


class RegistryServerDocument(BaseModel):
    """The parts of an MCP Registry server.json the gateway reads; every other key is ignored.

    Packages describe local installs the gateway cannot run, so only the
    remotes are kept.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str | None = Field(
        default=None, description="Registry name, such as 'io.github.acme/weather'"
    )
    description: str | None = Field(default=None, description="What the server does")
    website_url: str | None = Field(
        default=None, alias="websiteUrl", description="The server's website"
    )
    remotes: Annotated[list[RegistryRemote], valid_entries(RegistryRemote)] = Field(
        default_factory=list, description="Network remotes, in the document's order"
    )

    @property
    def first_usable_remote(self) -> RegistryRemote | None:
        """The first remote the gateway can reach the server through, if any."""
        return next((remote for remote in self.remotes if remote.is_usable), None)
