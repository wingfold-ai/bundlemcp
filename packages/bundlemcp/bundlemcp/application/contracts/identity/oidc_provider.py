from typing import Protocol, runtime_checkable

from bundlemcp.domain.access.oidc_claims import OidcClaims


@runtime_checkable
class OidcProvider(Protocol):
    """The identity provider admins log in with.

    Both methods raise ``OidcUnavailable`` while the provider cannot be reached
    yet, so a caller can tell "try again shortly" from a refused login.
    """

    async def authorize_url(
        self, *, state: str, nonce: str, redirect_uri: str, code_challenge: str
    ) -> str: ...

    async def exchange(
        self, *, code: str, redirect_uri: str, nonce: str, code_verifier: str
    ) -> OidcClaims: ...
