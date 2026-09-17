"""The OAuth 2.1 authorization server's business logic, free of HTTP."""

from bundlemcp.application.contracts.identity.client_metadata_fetcher import ClientMetadataFetcher
from bundlemcp.application.oauth_server.authorization_code_grant import AuthorizationCodeGrant
from bundlemcp.application.oauth_server.authorization_code_issuer import AuthorizationCodeIssuer
from bundlemcp.application.oauth_server.authorization_request import AuthorizationRequest
from bundlemcp.application.oauth_server.authorization_service import AuthorizationService
from bundlemcp.application.oauth_server.client_authenticator import OAuthClientAuthenticator
from bundlemcp.application.oauth_server.client_registration_service import (
    ClientRegistrationService,
)
from bundlemcp.application.oauth_server.client_resolver import ClientResolver
from bundlemcp.application.oauth_server.client_source import ClientSource, ClientSourceFactory
from bundlemcp.application.oauth_server.consent_service import ConsentService
from bundlemcp.application.oauth_server.introspection_service import TokenIntrospectionService
from bundlemcp.application.oauth_server.metadata_document_client_source import (
    MetadataDocumentClientSource,
)
from bundlemcp.application.oauth_server.pending_authorization import PendingAuthorization
from bundlemcp.application.oauth_server.refresh_token_grant import RefreshTokenGrant
from bundlemcp.application.oauth_server.registered_client_source import RegisteredClientSource
from bundlemcp.application.oauth_server.token_grant import TokenGrant, TokenGrantFactory
from bundlemcp.application.oauth_server.token_issuer import TokenIssuer
from bundlemcp.application.oauth_server.token_purge_service import TokenPurgeService
from bundlemcp.application.oauth_server.token_request import TokenRequest
from bundlemcp.application.oauth_server.token_service import OAuthTokenService
from bundlemcp.application.oauth_server.user_provisioning_service import (
    UserProvisioningService,
    VerifiedClaims,
)
from bundlemcp.domain.oauth.client_credentials import ClientCredentials
from bundlemcp.domain.oauth.client_id_metadata_document import (
    ClientIdMetadataDocument,
)

__all__ = [
    "AuthorizationCodeGrant",
    "AuthorizationCodeIssuer",
    "AuthorizationRequest",
    "AuthorizationService",
    "ClientCredentials",
    "ClientIdMetadataDocument",
    "ClientMetadataFetcher",
    "ClientRegistrationService",
    "ClientResolver",
    "ClientSource",
    "ClientSourceFactory",
    "ConsentService",
    "OAuthClientAuthenticator",
    "MetadataDocumentClientSource",
    "OAuthTokenService",
    "PendingAuthorization",
    "RefreshTokenGrant",
    "RegisteredClientSource",
    "TokenGrant",
    "TokenGrantFactory",
    "TokenIntrospectionService",
    "TokenIssuer",
    "TokenPurgeService",
    "TokenRequest",
    "UserProvisioningService",
    "VerifiedClaims",
]
