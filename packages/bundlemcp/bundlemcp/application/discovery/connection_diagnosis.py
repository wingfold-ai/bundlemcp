from pydantic import BaseModel, Field

from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata


class ConnectionDiagnosis(BaseModel):
    """What a failed probe means, settled with whatever the OAuth chain adds to it."""

    state: ConnectionState = Field(description="The connection state the failure points to")
    oauth: UpstreamMetadata | None = Field(
        default=None,
        description="The upstream's authorization server metadata, when it publishes usable "
        "OAuth metadata",
    )
    oauth_problem: str | None = Field(
        default=None,
        description="Why OAuth metadata the upstream points to cannot be used, when it cannot",
    )
