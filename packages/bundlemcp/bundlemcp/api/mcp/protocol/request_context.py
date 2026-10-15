from typing import Any

from pydantic import Field

from bundlemcp.api.mcp.protocol.dialect import CacheHint, ProtocolEra, WireDialect
from bundlemcp.api.mcp.protocol.endpoint_context import EndpointContext
from bundlemcp.api.mcp.protocol.server_info import server_info
from bundlemcp.domain.sessions.session_record import SessionRecord


class RequestContext(EndpointContext):
    """An admitted request, with the protocol facts every handler needs.

    Handshake-era requests get these facts from the session record they carry;
    modern-era requests carry them in ``_meta``. Handlers do not know which.
    """

    dialect: WireDialect = Field(description="The revision-specific wire shape for this client")
    client_capabilities: dict[str, Any] = Field(
        description="What the client said it supports, which gates the requests for client "
        "input an upstream may make"
    )
    log_level: str | None = Field(
        description="Minimum level of upstream log messages the client asked for; None when "
        "it asked for none"
    )
    routing_key: str = Field(
        description="Key under which this request's streams, calls and signals are addressed: "
        "the session id for handshake clients, a fresh id per modern request"
    )
    session: SessionRecord | None = Field(
        description="The session a handshake client opened; None for a modern request, which "
        "has no session by design"
    )

    @property
    def era(self) -> ProtocolEra:
        return self.dialect.era

    @property
    def call_key(self) -> str:
        """Key an in-flight call is registered under, and a cancellation addressed to.

        A handshake client's calls belong to its session. A modern request has
        none, so its calls belong to the caller on this endpoint: a later request
        with the same credentials can cancel one by its request id, and no other
        caller can. An anonymous modern caller is indistinguishable from any
        other, so its calls stay addressable only by the request's own key.
        """
        if self.session is not None or self.identity.sub is None:
            return self.routing_key
        return f"call:{self.view.endpoint.id}:{self.identity.sub}"

    @property
    def server_info(self) -> dict[str, Any]:
        return server_info(self.view.bundle.name)

    def shape(self, result: dict[str, Any], cache_hint: CacheHint | None = None) -> dict[str, Any]:
        """A result as this client's revision expects it."""
        return self.dialect.shape_result(
            result, server_info=self.server_info, cache_hint=cache_hint
        )
