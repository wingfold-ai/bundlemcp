from bundlemcp.oauth.upstream_client.needs_connect import NeedsConnect
from bundlemcp.oauth.upstream_client.upstream_metadata import UpstreamMetadata
from bundlemcp.oauth.upstream_client.upstream_tokens import UpstreamTokens


class HttpxUpstreamProvider:
    """Real upstream IdP interaction via httpx (deployment path).

    Discovery follows the RFC 9728 → RFC 8414 chain from the server's origin;
    the auth-code flow uses PKCE. Injected fakes replace this in tests.
    """

    def __init__(self, settings) -> None:
        self._settings = settings

    async def discover(self, server_url: str) -> UpstreamMetadata:
        from urllib.parse import urlparse

        import httpx

        origin = "{0.scheme}://{0.netloc}".format(urlparse(server_url))
        async with httpx.AsyncClient(timeout=10) as client:
            # try protected-resource metadata first, else AS metadata at the origin
            for path in (
                "/.well-known/oauth-protected-resource",
                "/.well-known/oauth-authorization-server",
            ):
                resp = await client.get(origin + path)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if "authorization_servers" in data:  # protected-resource doc
                    as_url = data["authorization_servers"][0].rstrip("/")
                    resp = await client.get(as_url + "/.well-known/oauth-authorization-server")
                    resp.raise_for_status()
                    data = resp.json()
                return UpstreamMetadata(
                    authorization_endpoint=data["authorization_endpoint"],
                    token_endpoint=data["token_endpoint"],
                    registration_endpoint=data.get("registration_endpoint"),
                    scopes_supported=data.get("scopes_supported", []),
                )
        raise NeedsConnect("upstream", "no_oauth_metadata")

    def authorize_url(self, meta, *, client_id, redirect_uri, state, code_challenge, scope) -> str:
        from urllib.parse import urlencode

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
        self, meta, *, code, redirect_uri, code_verifier, client_id, client_secret
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

    async def refresh(self, meta, *, refresh_token, client_id, client_secret) -> UpstreamTokens:
        return await self._token_request(
            meta,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            client_secret,
        )

    async def _token_request(self, meta, data: dict, client_secret: str | None) -> UpstreamTokens:
        import httpx

        if client_secret:
            data["client_secret"] = client_secret
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(meta.token_endpoint, data=data)
            resp.raise_for_status()
            payload = resp.json()
        return UpstreamTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
        )
