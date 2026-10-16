from typing import Literal

from pydantic import BaseModel, Field

from bundlemcp.domain.servers.connection_state import ConnectionState


class InspectorFailure(BaseModel):
    """Why the inspector got no MCP answer from its target; the 'failure' stream event."""

    type: Literal["failure"] = Field(
        default="failure", description="Names the stream event this payload is"
    )
    connection_state: ConnectionState = Field(
        description="What the gateway found out about the target, e.g. 'egress_denied', "
        "'unreachable' or 'credential_required'"
    )
    detail: str = Field(description="A sentence saying what that state means")
