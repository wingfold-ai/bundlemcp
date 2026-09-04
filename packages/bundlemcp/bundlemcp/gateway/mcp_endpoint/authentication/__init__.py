"""Who is calling an endpoint, and what to answer when nobody is."""

from bundlemcp.gateway.mcp_endpoint.authentication.anonymous_authenticator import (
    AnonymousAuthenticator,
)
from bundlemcp.gateway.mcp_endpoint.authentication.api_key_authenticator import (
    ApiKeyAuthenticator,
)
from bundlemcp.gateway.mcp_endpoint.authentication.auth_challenge import unauthorized_challenge
from bundlemcp.gateway.mcp_endpoint.authentication.credential_authenticator import (
    CredentialAuthenticator,
)
from bundlemcp.gateway.mcp_endpoint.authentication.endpoint_authentication import (
    DEFAULT_PRECEDENCE,
    EndpointAuthentication,
)
from bundlemcp.gateway.mcp_endpoint.authentication.oauth_bearer_authenticator import (
    OAuthBearerAuthenticator,
)

__all__ = [
    "DEFAULT_PRECEDENCE",
    "AnonymousAuthenticator",
    "ApiKeyAuthenticator",
    "CredentialAuthenticator",
    "EndpointAuthentication",
    "OAuthBearerAuthenticator",
    "unauthorized_challenge",
]
