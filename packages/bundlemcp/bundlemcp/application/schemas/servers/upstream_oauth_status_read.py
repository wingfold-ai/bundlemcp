from pydantic import BaseModel, Field

from bundlemcp.application.schemas.servers.upstream_connection_status import (
    UpstreamConnectionStatus,
)
from bundlemcp.domain.servers.identity_mode import IdentityMode
from bundlemcp.domain.upstream_oauth.client_identification import ClientIdentification
from bundlemcp.domain.upstream_oauth.upstream_grant import UpstreamGrant


class UpstreamOAuthStatusRead(BaseModel):
    """Connection state of a server's upstream OAuth, never its token values."""

    identity_mode: IdentityMode = Field(
        description="Whether callers share one upstream identity or each connects their own"
    )
    configured: bool = Field(
        description="Whether this gateway can store upstream tokens at all; false until token "
        "encryption keys are configured"
    )
    shared: UpstreamConnectionStatus | None = Field(
        default=None,
        description="State of the shared connection; null when upstream OAuth is not configured",
    )
    client_id: str | None = Field(
        default=None,
        description="Client id registered at the upstream authorization server; null until set",
    )
    authorization_url: str | None = Field(
        default=None,
        description="Operator-configured authorization endpoint; null when it is discovered",
    )
    token_url: str | None = Field(
        default=None,
        description="Operator-configured token endpoint; null when it is discovered",
    )
    identification: ClientIdentification | None = Field(
        default=None,
        description="How the client came to be: 'preregistered' (an admin stored it), "
        "'metadata_document' (the gateway's own client metadata URL is its id) or "
        "'dynamic_registration'; null until there is a client",
    )
    grant_type: UpstreamGrant = Field(
        default=UpstreamGrant.AUTHORIZATION_CODE,
        description="How tokens are obtained: through a browser sign-in, or with the client "
        "credentials grant",
    )
    step_up_scopes: list[str] = Field(
        default=[],
        description="Scopes the upstream demanded after connecting; the next connect requests "
        "them too",
    )
