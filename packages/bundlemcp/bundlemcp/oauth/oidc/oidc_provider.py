from typing import Protocol, runtime_checkable

from bundlemcp.oauth.oidc.oidc_claims import OidcClaims


@runtime_checkable
class OidcProvider(Protocol):
    def authorize_url(self, *, state: str, nonce: str, redirect_uri: str) -> str: ...

    async def exchange(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims: ...
