"""The per-user-upstream rule (UPS-30) as a pure decision over entities."""

from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.policies.per_user_upstream_policy import PerUserUpstreamPolicy
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.servers.server_auth_mode import ServerAuthMode

PER_USER = McpServer(
    name="gh",
    url="http://gh/mcp",
    auth_mode=ServerAuthMode.UPSTREAM_OAUTH,
    identity_mode=IdentityMode.PER_USER,
)
SHARED = McpServer(name="echo", url="http://echo/mcp")


def test_anonymous_endpoint_may_not_expose_a_per_user_server():
    assert not PerUserUpstreamPolicy.endpoint_may_expose([EndpointAuthMode.NONE], [PER_USER])
    assert PerUserUpstreamPolicy.endpoint_may_expose([EndpointAuthMode.NONE], [SHARED])
    assert PerUserUpstreamPolicy.endpoint_may_expose([EndpointAuthMode.OAUTH], [PER_USER])


def test_per_user_server_may_not_join_an_anonymously_exposed_bundle():
    import uuid

    bundle_id = uuid.uuid4()
    anonymous = Endpoint(name="open", bundle_id=bundle_id, auth_modes=[EndpointAuthMode.NONE])
    keyed = Endpoint(name="keyed", bundle_id=bundle_id, auth_modes=[EndpointAuthMode.API_KEY])
    assert not PerUserUpstreamPolicy.server_may_join(PER_USER, [keyed, anonymous])
    assert PerUserUpstreamPolicy.server_may_join(PER_USER, [keyed])
    assert PerUserUpstreamPolicy.server_may_join(SHARED, [anonymous])
