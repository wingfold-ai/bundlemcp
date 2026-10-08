from bundlemcp.application.settings.settings import Settings
from bundlemcp.infrastructure.oidc.discovering_oidc_provider import DiscoveringOidcProvider
from bundlemcp.infrastructure.oidc.jose_oidc_provider import JoseOidcProvider


def build_provider(settings: Settings) -> DiscoveringOidcProvider | None:
    """The configured identity provider, or None when admin login is disabled.

    Nothing is fetched here: the provider discovers its issuer once started, and
    keeps retrying while the issuer cannot be reached.
    """
    if not settings.oidc_discovery_url:
        return None
    return DiscoveringOidcProvider(lambda: JoseOidcProvider.discover(settings))
