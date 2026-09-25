"""Turning what an upstream answered into the state an operator acts on."""

from bundlemcp.domain.servers.connection_state import ConnectionState
from bundlemcp.domain.servers.observed_response import ObservedResponse

NOT_MCP_STATUSES = frozenset({404, 405, 406, 415})


def classify_refusal(observed: ObservedResponse | None, *, unreachable: bool) -> ConnectionState:
    """The state a failed probe points to, from the HTTP evidence alone.

    A refusal without OAuth evidence in the challenge is reported as
    ``credential_required``; whether the server nonetheless publishes OAuth
    metadata at a well-known location takes a network lookup, which the
    caller does before settling on it.
    """
    if unreachable:
        return ConnectionState.UNREACHABLE
    if observed is None:
        return ConnectionState.ERROR
    if observed.status == 403 and observed.challenge.is_insufficient_scope:
        return ConnectionState.INSUFFICIENT_SCOPE
    if observed.is_auth_refusal:
        if observed.challenge.names_oauth:
            return ConnectionState.OAUTH_REQUIRED
        return ConnectionState.CREDENTIAL_REQUIRED
    if observed.status in NOT_MCP_STATUSES and not observed.carries_jsonrpc:
        return ConnectionState.NOT_MCP
    if 200 <= observed.status < 300:  # answered, but with a body that is not MCP
        return ConnectionState.NOT_MCP
    return ConnectionState.ERROR
