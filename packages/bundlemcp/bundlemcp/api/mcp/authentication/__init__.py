"""Who is calling an endpoint, and what to answer when nobody is."""

from bundlemcp.api.mcp.authentication.anonymous_authenticator import (
    AnonymousAuthenticator,
)
from bundlemcp.api.mcp.authentication.api_key_authenticator import (
    ApiKeyAuthenticator,
)
from bundlemcp.api.mcp.authentication.auth_challenge import unauthorized_challenge
from bundlemcp.api.mcp.authentication.credential_authenticator import (
    CredentialAuthenticator,
)
from bundlemcp.api.mcp.authentication.endpoint_authentication import (
    DEFAULT_PRECEDENCE,
    EndpointAuthentication,
)
from bundlemcp.api.mcp.authentication.oauth_bearer_authenticator import (
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
