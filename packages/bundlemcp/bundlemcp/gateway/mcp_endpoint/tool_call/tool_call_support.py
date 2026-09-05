import asyncio

from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.gateway.audit import AuditWriter
from bundlemcp.gateway.mcp_endpoint.upstream_credentials import UpstreamCredentialResolver
from bundlemcp.gateway.metering import MeteringHook
from bundlemcp.gateway.runtime_config import RuntimeConfig
from bundlemcp.gateway.signals import SignalBus
from bundlemcp.gateway.streams import StreamRegistry
from bundlemcp.gateway.upstream import ClientFactory
from bundlemcp.store.sessions import SessionStore


class ToolCallSupport(BaseModel):
    """The collaborators every tools/call needs, held once by the handler."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    metering: MeteringHook = Field(description="Billing hook consulted before and after the call")
    audit: AuditWriter = Field(description="Where the call's audit record goes")
    credentials: UpstreamCredentialResolver = Field(
        description="Resolves the upstream Authorization header for the caller"
    )
    client_factory: ClientFactory = Field(description="Builds the MCP client for the upstream")
    sessions: SessionStore = Field(description="Records the upstream binding on the session")
    registry: StreamRegistry = Field(
        description="In-flight calls and reply futures on this replica"
    )
    signals: SignalBus = Field(description="Reaches the replica holding the client's stream")
    runtime_config: RuntimeConfig = Field(description="Source of the call timeouts")
    metering_fail_open: bool = Field(
        description="Whether a call proceeds when the metering hook itself fails"
    )
    detached: set[asyncio.Task] = Field(
        default_factory=set,
        description="Accounting tasks for calls whose client disconnected, kept alive until done",
    )
