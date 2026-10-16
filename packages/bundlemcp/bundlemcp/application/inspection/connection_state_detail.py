"""What each connection state means, in a sentence an operator can act on."""

from bundlemcp.domain.servers.connection_state import ConnectionState

CONNECTION_STATE_DETAIL = {
    ConnectionState.OAUTH_REQUIRED: "The target requires OAuth sign-in.",
    ConnectionState.ACCOUNT_REQUIRED: "No upstream account is connected for this target.",
    ConnectionState.CREDENTIAL_REQUIRED: "The target refused the request without a usable "
    "credential.",
    ConnectionState.INSUFFICIENT_SCOPE: "The credential lacks a permission the target needs.",
    ConnectionState.NOT_MCP: "The URL is not a Streamable HTTP MCP endpoint.",
    ConnectionState.UNREACHABLE: "The target could not be reached (connection, TLS or timeout).",
    ConnectionState.EGRESS_DENIED: "The gateway's egress policy does not allow this address.",
    ConnectionState.ERROR: "The target answered with an error.",
}


def connection_state_detail(state: ConnectionState) -> str:
    return CONNECTION_STATE_DETAIL.get(state, "The target gave no MCP answer.")
