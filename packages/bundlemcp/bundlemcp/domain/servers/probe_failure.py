from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.observed_response import ObservedResponse


class ProbeFailure(Exception):
    """A probe that did not get an MCP answer, with what the upstream did instead."""

    def __init__(
        self,
        message: str,
        *,
        state: ConnectionState,
        observed: ObservedResponse | None = None,
    ) -> None:
        self.state = state
        self.observed = observed
        super().__init__(message)
