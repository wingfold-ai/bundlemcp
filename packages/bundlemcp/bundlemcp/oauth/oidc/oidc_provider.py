from typing import Protocol

from bundlemcp.oauth.oidc.oidc_claims import OidcClaims


class OidcProvider(Protocol):
    def authorize_url(self, *, state: str, nonce: str, redirect_uri: str) -> str: ...

    async def exchange(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims: ...
