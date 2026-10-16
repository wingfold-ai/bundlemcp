from pydantic import Field

from bundlemcp.application.bootstrap.bootstrap_oauth_client import BootstrapOAuthClient
from bundlemcp.application.bootstrap.secret_ref import SecretRef
from bundlemcp.application.schemas import ServerUpsert


class BootstrapServer(ServerUpsert):
    """A server in a bootstrap document, with the upstream OAuth client the API
    sets through a separate route.

    A header value or the client secret may be a placeholder that keeps what the
    target stores; the management API itself never accepts one.
    """

    static_headers: dict[str, str | SecretRef] = Field(  # type: ignore[assignment]
        default_factory=dict,
        description="Headers sent on every upstream request; a value may be a placeholder "
        "that keeps the stored value of that header. Empty keeps every stored header",
    )
    upstream_oauth: BootstrapOAuthClient | None = Field(
        default=None,
        description="The pre-registered OAuth client the gateway presents to this server's "
        "authorization server. Needs token encryption keys; omit it for a server that is not "
        "behind upstream OAuth, or whose client the gateway registers itself",
    )
