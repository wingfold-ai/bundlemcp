from pydantic import Field

from bundlemcp.application.schemas import ServerUpsert, UpstreamOAuthConfig


class BootstrapServer(ServerUpsert):
    """A server in a bootstrap document, with the upstream OAuth client the API
    sets through a separate route."""

    upstream_oauth: UpstreamOAuthConfig | None = Field(  # MGMT-16
        default=None,
        description="The pre-registered OAuth client the gateway presents to this server's "
        "authorization server. Needs token encryption keys; omit it for a server that is not "
        "behind upstream OAuth, or whose client the gateway registers itself",
    )
