from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from bundlemcp.application.contracts.inspection.inspector_client import InspectorClient


@runtime_checkable
class GatewayEndpointClientFactory(Protocol):
    """Opens an MCP connection to one of this gateway's own endpoints.

    The request enters the endpoint's public route as any client's would, so
    authentication, the profile, curation, metering, rate limits and audit all
    apply, but it never leaves the process. ``headers`` carry the endpoint
    credential; ``client_ip`` is the address the request is attributed to.
    Failures raise ``ProbeFailure`` as ``InspectorConnector`` does.
    """

    def open(
        self, endpoint: str, headers: dict[str, str], *, client_ip: str
    ) -> AbstractAsyncContextManager[InspectorClient]: ...
