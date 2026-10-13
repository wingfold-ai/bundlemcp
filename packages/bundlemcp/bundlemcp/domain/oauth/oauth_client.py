from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.application_type import ApplicationType
from bundlemcp.domain.oauth.client_id_metadata_document import ClientIdMetadataDocument
from bundlemcp.domain.oauth.grant_type import GrantType
from bundlemcp.domain.oauth.token_endpoint_auth_method import TokenEndpointAuthMethod
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class OAuthClient(BaseModel):
    client_id: str = Field(description="Identifier issued to the client")
    client_secret_hash: str | None = Field(
        default=None,
        description="Hash of the client secret. Null marks a public client, which proves "
        "itself with PKCE instead",
    )
    client_name: str | None = Field(
        default=None, description="Name shown to the user on the consent screen"
    )
    redirect_uris: list[str] = Field(
        default_factory=list,
        description="URIs the authorization response may be sent to",
    )
    grant_types: list[GrantType] = Field(
        default_factory=lambda: [GrantType.AUTHORIZATION_CODE, GrantType.REFRESH_TOKEN],
        description="Grant types this client registered for",
    )
    token_endpoint_auth_method: TokenEndpointAuthMethod = Field(
        default=TokenEndpointAuthMethod.NONE,
        description="How the client authenticates at the token endpoint",
    )
    scope: str = Field(default="mcp", description="Space-separated scopes the client may request")
    application_type: ApplicationType | None = Field(
        default=None,
        description="'web' or 'native' as the client registered itself; absent when it did not "
        "say or was described by a metadata document",
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        description="When the client registered",
    )
    last_used_at: datetime | None = Field(
        default=None,
        description="When the client last obtained a token. Clients that never used one are "
        "purged, so abandoned registrations do not accumulate",
    )

    @property
    def is_public(self) -> bool:
        """A client with no secret, which proves itself with PKCE instead."""
        return self.token_endpoint_auth_method == TokenEndpointAuthMethod.NONE

    def verifies_secret(self, presented: str | None, hasher: SecretHasher) -> bool:
        """Whether a presented secret is this confidential client's; a public client has none."""
        if presented is None or self.client_secret_hash is None:
            return False
        return hasher.matches(presented, self.client_secret_hash)

    def allows_grant(self, grant_type: GrantType) -> bool:
        """Whether the client registered for this grant; the token endpoint refuses the rest."""
        return grant_type in self.grant_types

    def apply_metadata_document(self, document: ClientIdMetadataDocument) -> None:
        """Mirror what the client publishes about itself, keeping what this gateway recorded.

        The identifier, creation time and last use stay; everything the
        document describes is replaced, so a changed document takes effect
        the next time it is applied.
        """
        self.client_name = document.client_name
        self.redirect_uris = list(document.redirect_uris)
        self.grant_types = list(document.grant_types)
        self.scope = document.scope or "mcp"
