"""Classifying why an MCP client connection got no answer."""

import httpx2

from bundlemcp.domain.servers.connection_classifier import classify_refusal
from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.probe_failure import ProbeFailure
from bundlemcp.domain.servers.response_log import ResponseLog
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, HostUnresolvable

TRANSPORT_FAILURES = (httpx2.TransportError, OSError, TimeoutError)


def in_chain[E: BaseException](
    exc: BaseException, kinds: type[E] | tuple[type[E], ...]
) -> E | None:
    """The first exception of ``kinds`` in ``exc``'s cause chain, including exception groups.

    The MCP client wraps what its connection raised, so an egress denial at
    connect time arrives as the cause of a generic connection error.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, kinds):
            return current
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if (linked := current.__cause__ or current.__context__) is not None:
            pending.append(linked)
    return None


def connection_failure(exc: BaseException, responses: ResponseLog) -> ProbeFailure:
    """The classified failure behind ``exc``, from the HTTP responses the transport saw."""
    if (unresolved := in_chain(exc, HostUnresolvable)) is not None:
        return ProbeFailure(str(unresolved), state=ConnectionState.UNREACHABLE)
    if (denied := in_chain(exc, EgressDenied)) is not None:
        return ProbeFailure(str(denied), state=ConnectionState.EGRESS_DENIED)
    observed = responses.last
    unreachable = observed is None and in_chain(exc, TRANSPORT_FAILURES) is not None
    state = classify_refusal(observed, unreachable=unreachable)
    message = f"HTTP {observed.status}: {exc}" if observed is not None else str(exc)
    return ProbeFailure(message, state=state, observed=observed)
