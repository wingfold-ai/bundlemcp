"""The real upstream authorization server, reached over HTTP."""

from urllib.parse import urlencode, urlparse

import httpx

from bundlemcp.oauth.upstream_client.needs_connect import NeedsConnect
from bundlemcp.oauth.upstream_client.upstream_metadata import UpstreamMetadata
from bundlemcp.oauth.upstream_client.upstream_tokens import UpstreamTokens
from bundlemcp.settings import Settings

HTTP_TIMEOUT = 10
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"


class HttpxUpstreamProvider:
    """Discovery follows the RFC 9728 → RFC 8414 chain from the server's origin;
    the auth-code flow uses PKCE. Injected fakes replace this in tests."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def discover(self, server_url: str) -> UpstreamMetadata:
        origin = "{0.scheme}://{0.netloc}".format(urlparse(server_url))
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # try protected-resource metadata first, else AS metadata at the origin
            for path in (PROTECTED_RESOURCE_PATH, AUTHORIZATION_SERVER_PATH):
                response = await client.get(origin + path)
                if response.status_code != 200:
                    continue
                data = response.json()
                if "authorization_servers" in data:  # protected-resource doc
                    as_url = data["authorization_servers"][0].rstrip("/")
                    response = await client.get(as_url + AUTHORIZATION_SERVER_PATH)
                    response.raise_for_status()
                    data = response.json()
                return UpstreamMetadata(
                    authorization_endpoint=data["authorization_endpoint"],
                    token_endpoint=data["token_endpoint"],
                    registration_endpoint=data.get("registration_endpoint"),
                    scopes_supported=data.get("scopes_supported", []),
                    issuer=data.get("issuer"),
                    authorization_response_iss_parameter_supported=bool(
                        data.get("authorization_response_iss_parameter_supported", False)
                    ),
                )
        raise NeedsConnect("upstream", "no_oauth_metadata")

    def authorize_url(
        self,
        meta: UpstreamMetadata,
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str | None,
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if scope:
            params["scope"] = scope
        return f"{meta.authorization_endpoint}?{urlencode(params)}"

    async def exchange(
        self,
        meta: UpstreamMetadata,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        client_id: str,
        client_secret: str | None,
    ) -> UpstreamTokens:
        return await self._token_request(
            meta,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "client_id": client_id,
            },
            client_secret,
        )

    async def refresh(
        self,
        meta: UpstreamMetadata,
        *,
        refresh_token: str,
        client_id: str,
        client_secret: str | None,
    ) -> UpstreamTokens:
        return await self._token_request(
            meta,
            {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id},
            client_secret,
        )

    async def _token_request(
        self, meta: UpstreamMetadata, data: dict[str, str], client_secret: str | None
    ) -> UpstreamTokens:
        if client_secret:
            data["client_secret"] = client_secret
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(meta.token_endpoint, data=data)
            response.raise_for_status()
            payload = response.json()
        return UpstreamTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
        )
