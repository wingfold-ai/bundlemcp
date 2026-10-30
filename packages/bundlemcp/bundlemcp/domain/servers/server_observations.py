from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.health_status import HealthStatus
from bundlemcp.domain.servers.server_capabilities import ServerCapabilities


class ServerObservations(BaseModel):
    """What contacting an upstream found out about it, as opposed to how it is configured.

    Probes and live calls write these and nothing else of a server, so a rename or a
    configuration change saved while they ran is never overwritten by the copy they read.
    """

    model_config = ConfigDict(frozen=True)

    capabilities: ServerCapabilities = Field(
        description="What the server advertised at its last successful probe"
    )
    protocol_version: str | None = Field(
        description="MCP revision negotiated at the last successful probe, absent until then"
    )
    health_status: HealthStatus = Field(description="Result of the most recent contact")
    last_error: str | None = Field(description="Why the server was marked failing, if it is")
    connection_state: ConnectionState = Field(
        description="What the last probe found out about the upstream"
    )
    last_discovered_at: datetime | None = Field(
        description="When a probe last read the server's tools successfully; None until one has"
    )
