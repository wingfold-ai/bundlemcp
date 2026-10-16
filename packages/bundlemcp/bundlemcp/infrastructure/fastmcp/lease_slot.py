"""The part of a pooled upstream session that changes with each request it serves."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from bundlemcp.domain.servers.observed_response import ObservedResponse
from bundlemcp.domain.servers.response_log import ResponseLog

MCP_SESSION_ID = "mcp-session-id"
MCP_PROTOCOL_VERSION = "mcp-protocol-version"


class LeaseSlot(BaseModel):
    """What the current lease of one pooled session puts on the wire, and where answers go.

    A pooled transport outlives every request it serves, so whatever is
    specific to a request — its credentials, its relay callbacks, its response
    log — is read from here when the transport needs it rather than fixed when
    it was built. Between requests the last headers stay in place, so the
    session's own event stream can reconnect.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers added to every request of the current lease, and kept for the "
        "session's own stream between leases",
    )
    handlers: dict[str, Any] = Field(
        default_factory=dict,
        description="The current lease's relay callbacks; empty between leases",
    )
    responses: ResponseLog | None = Field(
        default=None, description="The current lease's response log; None between leases"
    )
    session_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Session id and protocol version a continued upstream session is addressed "
        "with, since its transport never saw the initialize that set them",
    )

    def begin(self, headers: dict[str, str], handlers: dict[str, Any], log: ResponseLog) -> None:
        self.headers = headers
        self.handlers = handlers
        self.responses = log

    def finish(self) -> None:
        self.handlers = {}
        self.responses = None

    def request_headers(self) -> dict[str, str]:
        return {**self.headers, **self.session_headers}

    def continue_session(self, session_id: str, protocol_version: str | None) -> None:
        self.session_headers = {MCP_SESSION_ID: session_id}
        if protocol_version is not None:
            self.session_headers[MCP_PROTOCOL_VERSION] = protocol_version


class SlotResponseLog(ResponseLog):
    """The response log a pooled transport is built with: it records into the current lease's.

    What arrives between leases — on the session's own event stream — belongs
    to no request and is dropped.
    """

    _slot: LeaseSlot = PrivateAttr()

    def __init__(self, slot: LeaseSlot) -> None:
        super().__init__()
        self._slot = slot

    def record(self, response: ObservedResponse) -> None:
        if self._slot.responses is not None:
            self._slot.responses.record(response)

    def record_transport_failure(self) -> None:
        if self._slot.responses is not None:
            self._slot.responses.record_transport_failure()

    def record_unsent(self) -> None:
        if self._slot.responses is not None:
            self._slot.responses.record_unsent()

    def record_oversized(self, limit: int) -> None:
        if self._slot.responses is not None:
            self._slot.responses.record_oversized(limit)
