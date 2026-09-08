from bundlemcp.application.contracts.identity.oidc_provider import OidcProvider
from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.oidc.jose_oidc_provider import JoseOidcProvider


async def build_provider(settings: Settings) -> OidcProvider | None:
    """The configured identity provider, or None when admin login is disabled."""
    if not settings.oidc_discovery_url:
        return None
    return await JoseOidcProvider.discover(settings)
