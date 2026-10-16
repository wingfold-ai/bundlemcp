from pydantic import Field

from bundlemcp.application.bootstrap.secret_ref import SecretRef
from bundlemcp.application.schemas import UpstreamOAuthConfig


class BootstrapOAuthClient(UpstreamOAuthConfig):
    """An upstream OAuth client in a document, whose secret may be a placeholder."""

    client_secret: str | SecretRef | None = Field(  # type: ignore[assignment]
        default=None,
        description="The client secret, or a placeholder that keeps the one the target "
        "stores; omit it for a public client",
    )
