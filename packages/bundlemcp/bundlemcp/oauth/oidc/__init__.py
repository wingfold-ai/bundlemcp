"""OIDC relying-party login + admin session lifecycle.

The IdP interaction is behind OidcProvider so hermetic tests inject a fake
issuer instead of reaching a real Keycloak.
"""

from bundlemcp.oauth.oidc.authlib_oidc_provider import AuthlibOidcProvider
from bundlemcp.oauth.oidc.build_provider import build_provider
from bundlemcp.oauth.oidc.oidc_claims import OidcClaims
from bundlemcp.oauth.oidc.oidc_error import OidcError
from bundlemcp.oauth.oidc.oidc_provider import OidcProvider

__all__ = [
    "AuthlibOidcProvider",
    "OidcClaims",
    "OidcError",
    "OidcProvider",
    "build_provider",
]
