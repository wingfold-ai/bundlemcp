from bundlemcp.oauth.oidc.authlib_oidc_provider import AuthlibOidcProvider
from bundlemcp.oauth.oidc.oidc_provider import OidcProvider
from bundlemcp.settings import Settings


async def build_provider(settings: Settings) -> OidcProvider | None:
    """The configured identity provider, or None when admin login is disabled."""
    if not settings.oidc_discovery_url:
        return None
    return await AuthlibOidcProvider.discover(settings)
