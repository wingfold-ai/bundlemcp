from enum import StrEnum
from typing import Self

from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.domain.servers.upstream_reach import CONNECTION_CLOSED


class UpstreamFailure(StrEnum):
    """How a request to an upstream session failed, as far as a retry is concerned."""

    SESSION_EXPIRED = "session_expired"  # the upstream answered 404 for the session
    NOT_SENT = "not_sent"  # the connection failed before the request went out
    LOST_AFTER_SEND = "lost_after_send"  # the request went out; its answer never came

    @classmethod
    def of(cls, responses: ResponseLog, *, jsonrpc_code: int | None) -> Self | None:
        """What a request that raised says about its session, or None for any other failure.

        ``jsonrpc_code`` is the code of the JSON-RPC error the request raised, if
        it raised one. A 404 is how a Streamable HTTP upstream says it no longer
        knows the session; an upstream's own error, a refused credential or the
        gateway's response cap are not failures of the session.
        """
        if responses.oversized_limit is not None:
            return None
        if any(observed.status == 404 for observed in responses.responses):
            return cls.SESSION_EXPIRED
        if responses.unsent:
            return cls.NOT_SENT
        if responses.transport_failed or (
            jsonrpc_code == CONNECTION_CLOSED and responses.last is None
        ):
            return cls.LOST_AFTER_SEND
        return None
