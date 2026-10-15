"""The identity header the gateway adds, and the client values it never forwards (AUTH-29)."""

import pytest
from bundlemcp.api.mcp.protocol.header_forwarding import HeaderForwarding
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.access.identity_subject import IdentitySubject
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.servers.mcp_server import McpServer

CALLER = CallerIdentity(auth_method=EndpointAuthMode.OAUTH, user_id="u-1")


@pytest.mark.parametrize(
    "mapping",
    [{"x-mcp-user": "x-mcp-user"}, {"x-client": "X-Mcp-User"}, {"x-client": "x-mcp-user"}],
    ids=["same-name-lowercase", "renamed-mixed-case", "renamed-lowercase"],
)
@pytest.mark.parametrize("send_identity", [True, False], ids=["identity-on", "identity-off"])
def test_auth29_client_identity_value_is_never_forwarded(mapping, send_identity):
    """AUTH-29: however a mapping spells the identity header, the client's value is stripped."""
    server = McpServer(
        name="notes",
        url="http://notes:8000/mcp",
        forward_headers=mapping,
        send_identity_header=send_identity,
    )
    client = {"x-mcp-user": "spoofed", "x-client": "spoofed"}
    extra = HeaderForwarding(IdentitySubject.INTERNAL).headers_for(client, server, CALLER)
    values = [v for name, v in extra.items() if name.lower() == "x-mcp-user"]
    assert "spoofed" not in values
    assert values == (["u-1"] if send_identity else [])
