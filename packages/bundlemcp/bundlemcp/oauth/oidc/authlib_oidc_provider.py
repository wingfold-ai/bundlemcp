"""The real identity provider, reached over HTTP with authlib verifying its tokens."""

from typing import Any, Self
from urllib.parse import urlencode

import httpx
from authlib.jose import jwt

from bundlemcp.oauth.oidc.oidc_claims import OidcClaims
from bundlemcp.oauth.oidc.oidc_error import OidcError
from bundlemcp.settings import Settings


class AuthlibOidcProvider:
    """A provider is built from its discovery document, so it is ready once constructed."""

    def __init__(self, settings: Settings, metadata: dict[str, Any]) -> None:
        self._settings = settings
        self._metadata = metadata

    @classmethod
    async def discover(cls, settings: Settings) -> Self:
        """Fetch the issuer's discovery document and return a provider that can use it."""
        if not settings.oidc_discovery_url:
            raise OidcError("no OIDC discovery URL configured")
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.oidc_discovery_url)
            response.raise_for_status()
            return cls(settings, response.json())

    def authorize_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        return f"{self._metadata['authorization_endpoint']}?{urlencode(params)}"

    async def exchange(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                self._metadata["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self._settings.oidc_client_id,
                    "client_secret": self._settings.oidc_client_secret,
                },
            )
            token_response.raise_for_status()
            id_token = token_response.json()["id_token"]
            jwks_response = await client.get(self._metadata["jwks_uri"])
            jwks_response.raise_for_status()
        claims = jwt.decode(id_token, jwks_response.json())
        claims.validate()
        if claims.get("nonce") != nonce:
            raise OidcError("nonce mismatch")
        return OidcClaims(
            issuer=claims["iss"],
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            groups=claims.get("groups", []),
        )
