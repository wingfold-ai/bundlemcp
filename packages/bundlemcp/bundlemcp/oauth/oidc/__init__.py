"""OIDC relying-party login + admin session lifecycle.

The IdP interaction is behind OidcProvider so hermetic tests inject a fake
issuer instead of reaching a real Keycloak.
"""

from bundlemcp.oauth.oidc._common import OIDC_STATE_KEY, OIDC_STATE_TTL, log
from bundlemcp.oauth.oidc.authlib_oidc_provider import AuthlibOidcProvider
from bundlemcp.oauth.oidc.oidc_claims import OidcClaims
from bundlemcp.oauth.oidc.oidc_provider import OidcProvider
from bundlemcp.oauth.oidc.routes import (
    build_provider,
    is_admin,
    login,
    login_callback,
    logout,
    provision_user,
    router,
)

__all__ = [
    "OIDC_STATE_KEY",
    "OIDC_STATE_TTL",
    "AuthlibOidcProvider",
    "OidcClaims",
    "OidcProvider",
    "build_provider",
    "is_admin",
    "log",
    "login",
    "login_callback",
    "logout",
    "provision_user",
    "router",
]
