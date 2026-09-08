"""The rule that an anonymous endpoint never fronts a per-user upstream.

A server whose upstream OAuth identity is per user needs to know which user is
calling. An endpoint that accepts no credentials cannot say, so the two must
never meet through a bundle.
"""

from collections.abc import Iterable, Sequence

from bundlemcp.domain.endpoints.endpoint import Endpoint
from bundlemcp.domain.endpoints.endpoint_auth_mode import EndpointAuthMode
from bundlemcp.domain.servers.mcp_server import McpServer


class PerUserUpstreamPolicy:
    """Pure: every question is answered from the entities handed in."""

    @staticmethod
    def is_anonymous_only(auth_modes: Sequence[EndpointAuthMode]) -> bool:
        return set(auth_modes) == {EndpointAuthMode.NONE}

    @classmethod
    def endpoint_may_expose(
        cls, auth_modes: Sequence[EndpointAuthMode], members: Iterable[McpServer]
    ) -> bool:
        """Whether an endpoint with these modes may expose a bundle with these member servers."""
        if not cls.is_anonymous_only(auth_modes):
            return True
        return not any(server.requires_per_user_token for server in members)

    @staticmethod
    def server_may_join(server: McpServer, exposing_endpoints: Iterable[Endpoint]) -> bool:
        """Whether a server may be a member of a bundle these endpoints expose."""
        if not server.requires_per_user_token:
            return True
        return not any(endpoint.is_anonymous_only for endpoint in exposing_endpoints)
