from enum import StrEnum

from bundlemcp.domain.servers.response_log import ResponseLog

# the JSON-RPC code the MCP client uses for a connection that closed under it
CONNECTION_CLOSED = -32000


class UpstreamReach(StrEnum):
    """Whether a failed upstream call got as far as the upstream, for its health.

    ``unreachable`` counts toward the server's failure streak, ``answered``
    resets it, and ``undecided`` leaves it alone: a refused credential, a
    timeout, a cancellation or the gateway's own response cap say nothing
    about whether the upstream is up.
    """

    ANSWERED = "answered"
    UNREACHABLE = "unreachable"
    UNDECIDED = "undecided"

    @classmethod
    def of_failure(cls, responses: ResponseLog, *, jsonrpc_code: int | None) -> "UpstreamReach":
        """What a call that raised tells about its upstream.

        ``jsonrpc_code`` is the code of the JSON-RPC error the call raised, if
        it raised one.
        """
        if responses.oversized_limit is not None:
            return cls.UNDECIDED
        observed = responses.last
        if observed is not None:
            if observed.is_auth_refusal:
                return cls.UNDECIDED
            # a JSON body is the upstream's own JSON-RPC error; anything else is not MCP
            return cls.ANSWERED if observed.carries_jsonrpc else cls.UNREACHABLE
        if responses.transport_failed or jsonrpc_code == CONNECTION_CLOSED:
            return cls.UNREACHABLE
        if jsonrpc_code is not None:
            return cls.ANSWERED
        return cls.UNDECIDED
