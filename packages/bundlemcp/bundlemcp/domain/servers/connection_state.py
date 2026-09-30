from enum import StrEnum


class ConnectionState(StrEnum):
    """What the last attempt to reach an upstream server found out about it.

    Classified from the upstream's HTTP response rather than from the MCP
    client's error text, so each state names what an operator has to do.
    """

    UNKNOWN = "unknown"  # never probed
    READY = "ready"  # answered server/discover or initialize
    OAUTH_REQUIRED = "oauth_required"  # challenged with OAuth metadata
    ACCOUNT_REQUIRED = "account_required"  # upstream OAuth set up, no account connected yet
    INSUFFICIENT_SCOPE = "insufficient_scope"  # the token lacks a scope the server asked for
    CREDENTIAL_REQUIRED = "credential_required"  # refused without any OAuth metadata
    NOT_MCP = "not_mcp"  # the URL does not speak Streamable HTTP MCP
    UNREACHABLE = "unreachable"  # connection, TLS or timeout failure
    EGRESS_DENIED = "egress_denied"  # the egress policy refused the URL
    ERROR = "error"  # anything else

    @property
    def is_auth_problem(self) -> bool:
        """The server was reached but refused the gateway's credential, or it had none."""
        return self in {
            ConnectionState.OAUTH_REQUIRED,
            ConnectionState.ACCOUNT_REQUIRED,
            ConnectionState.INSUFFICIENT_SCOPE,
            ConnectionState.CREDENTIAL_REQUIRED,
        }
