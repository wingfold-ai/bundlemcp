"""Which client headers cross to an upstream, and the identity the gateway adds."""

from collections.abc import Mapping

from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.identity_subject import IdentitySubject
from bundlemcp.domain.servers.forward_header_rules import is_forwardable
from bundlemcp.domain.servers.mcp_server import McpServer

IDENTITY_HEADER = "X-MCP-User"  # spec 24


class HeaderForwarding:
    """The extra headers every upstream request carries, decided once per deployment.

    A server's configured header mappings pass client headers through, and the
    gateway adds its own identity header naming the caller in the configured
    namespace.
    """

    def __init__(self, identity_subject: IdentitySubject) -> None:
        self._identity_subject = identity_subject

    def headers_for(
        self, client_headers: Mapping[str, str], server: McpServer, identity: CallerIdentity
    ) -> dict[str, str]:
        """Build the extra headers forwarded to ``server`` for this caller.

        Applies the server's configured header mappings, skipping denied headers,
        then injects the gateway's own identity header (any client-supplied
        identity header is always stripped).
        """
        extra: dict[str, str] = {}
        for client_header, upstream_header in server.forward_headers.items():
            if not is_forwardable(client_header):  # FWD-2: also refused at write time (SRV-14)
                continue
            value = client_headers.get(client_header)
            if value is not None:
                extra[upstream_header] = value
        # client-supplied identity header is always stripped; gateway injects its own
        extra.pop(IDENTITY_HEADER, None)
        subject = identity.subject_for(self._identity_subject)  # FWD-3
        if server.send_identity_header and subject is not None:
            extra[IDENTITY_HEADER] = subject
        return extra
