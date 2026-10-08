from enum import StrEnum


class MeterOutcome(StrEnum):
    """How a metered tool call ended, as the metering hook is told after the call.

    The hook decides what each kind means for billing: an upstream that answered
    with an error result did run, unlike a call that produced no result at all.
    """

    RESULT = "result"
    """The upstream returned a tool result."""
    TOOL_ERROR = "tool_error"
    """The upstream returned a tool result marked ``isError``: the tool ran and reported failure."""
    NO_RESULT = "no_result"
    """No tool result: the upstream was unreachable or timed out, answered with a JSON-RPC
    error, the gateway refused the call after metering allowed it, or metering itself could
    not give an answer."""
    CANCELLED = "cancelled"
    """The client cancelled the call or closed its stream before a result arrived."""
