from urllib.parse import urlencode

from fastapi import HTTPException

from bundlemcp.oauth.oidc.oidc_claims import OidcClaims
from bundlemcp.settings import Settings


class AuthlibOidcProvider:
    """Real IdP via authlib (used in deployment; compose ships Keycloak)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._metadata: dict | None = None

    async def _load_metadata(self) -> dict:
        if self._metadata is None:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(self._settings.oidc_discovery_url)
                resp.raise_for_status()
                self._metadata = resp.json()
        return self._metadata

    def authorize_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        # discovery is async; deployment preloads metadata at startup. For the
        # authorize redirect we build from the known authorization endpoint.
        assert self._metadata is not None, "call preload() at startup"
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        return f"{self._metadata['authorization_endpoint']}?{urlencode(params)}"

    async def preload(self) -> None:
        await self._load_metadata()

    async def exchange(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims:
        import httpx
        from authlib.jose import jwt

        meta = await self._load_metadata()
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                meta["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self._settings.oidc_client_id,
                    "client_secret": self._settings.oidc_client_secret,
                },
            )
            token_resp.raise_for_status()
            id_token = token_resp.json()["id_token"]
            jwks_resp = await client.get(meta["jwks_uri"])
            jwks_resp.raise_for_status()
        claims = jwt.decode(id_token, jwks_resp.json())
        claims.validate()
        if claims.get("nonce") != nonce:
            raise HTTPException(400, "nonce mismatch")
        return OidcClaims(
            issuer=claims["iss"],
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            groups=claims.get("groups", []),
        )
