"""The real upstream authorization server, reached over HTTP."""

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, check_url_allowed

HTTP_TIMEOUT = 10
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"
OPENID_CONFIGURATION_PATH = "/.well-known/openid-configuration"
_RESOURCE_METADATA = re.compile(r'resource_metadata="([^"]+)"')

ClientFactory = Callable[[], httpx.AsyncClient]


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT)


def _split(url: str) -> tuple[str, str]:
    """The origin of a URL and its path without a trailing slash."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}", parsed.path.rstrip("/")


def _protected_resource_candidates(server_url: str) -> list[str]:
    """Where RFC 9728 puts the document: path-inserted first, then at the origin."""
    origin, path = _split(server_url)
    candidates = [f"{origin}{PROTECTED_RESOURCE_PATH}{path}"] if path else []
    candidates.append(f"{origin}{PROTECTED_RESOURCE_PATH}")
    return candidates


def _authorization_server_candidates(issuer: str) -> list[str]:
    """RFC 8414 and OpenID Connect metadata locations for an issuer, in the order to try."""
    origin, path = _split(issuer)
    candidates = [
        f"{origin}{AUTHORIZATION_SERVER_PATH}{path}",  # RFC 8414 path insertion
        f"{origin}{OPENID_CONFIGURATION_PATH}{path}",  # OIDC, path inserted
        f"{origin}{path}{OPENID_CONFIGURATION_PATH}",  # OIDC Discovery 1.0, appended
        f"{origin}{path}{AUTHORIZATION_SERVER_PATH}",  # appended, as some servers serve it
    ]
    return list(dict.fromkeys(candidates))


def _metadata(data: dict[str, Any]) -> UpstreamMetadata:
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


class HttpxUpstreamProvider:
    """Discovery follows the MCP authorization chain; the auth-code flow uses PKCE.
    Injected fakes replace this in tests.

    Discovery asks the server itself first: a 401 that names its protected
    resource document in ``WWW-Authenticate`` is followed. Otherwise the
    document is looked for where RFC 9728 puts it for the server's path, then
    at the origin. The authorization server it names is read through RFC 8414
    or OpenID Connect metadata, whichever it serves; a server with no protected
    resource document is tried as its own authorization server.

    Every URL this provider reaches passes the egress policy before a request
    is made: the server's origin, the documents and authorization server the
    remote side names, and the registration and token endpoints the metadata
    names. Those are chosen by the remote side, and the token request carries
    the gateway's client secret, so a document that points at a blocked address
    is refused rather than followed.
    """

    def __init__(self, settings: Settings, *, client_factory: ClientFactory = _default_client):
        self._settings = settings
        self._client_factory = client_factory

    async def discover(self, server_url: str) -> UpstreamMetadata:
        origin, _ = _split(server_url)
        self._check_egress(origin, "egress_denied")
        async with self._client_factory() as client:
            resource = await self._protected_resource(client, server_url)
            if resource is not None:
                servers = resource.get("authorization_servers") or []
                if servers:
                    issuer = servers[0].rstrip("/")
                    self._check_egress(issuer, "authorization_server_denied")
                    for url in _authorization_server_candidates(issuer):
                        data = await self._json(client, url)
                        if data is not None and "authorization_endpoint" in data:
                            return _metadata(data)
            # no protected resource document: the origin may be its own authorization server
            data = await self._json(client, origin + AUTHORIZATION_SERVER_PATH)
            if data is not None and "authorization_endpoint" in data:
                return _metadata(data)
        raise NeedsConnect("upstream", "no_oauth_metadata")

    async def _protected_resource(
        self, client: httpx.AsyncClient, server_url: str
    ) -> dict[str, Any] | None:
        # UPO-1: the MCP authorization spec's order, server-named document first
        candidates = _protected_resource_candidates(server_url)
        named = await self._named_resource_metadata(client, server_url)
        if named is not None:
            self._check_egress(named, "resource_metadata_denied")
            candidates.insert(0, named)
        for url in dict.fromkeys(candidates):
            data = await self._json(client, url)
            if data is not None and "authorization_servers" in data:
                return data
        return None

    @staticmethod
    async def _named_resource_metadata(client: httpx.AsyncClient, server_url: str) -> str | None:
        """The document URL a 401 from the server names, if it names one.

        Only the status and headers are read: a server that does not require a
        token may answer with an open event stream, which is not waited on.
        """
        try:
            async with client.stream(
                "GET", server_url, headers={"Accept": "text/event-stream"}
            ) as response:
                if response.status_code != 401:
                    return None
                named = _RESOURCE_METADATA.search(response.headers.get("www-authenticate", ""))
        except httpx.HTTPError:
            return None
        return named.group(1) if named else None

    @staticmethod
    async def _json(client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
        """The JSON object at a URL, or None when it is absent or not a JSON object."""
        response = await client.get(url)
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def register(
        self, meta: UpstreamMetadata, *, redirect_uri: str, client_name: str
    ) -> UpstreamClientRegistration:
        # UPO-1: RFC 7591 registration of a public client that proves itself with PKCE
        if not meta.registration_endpoint:
            raise NeedsConnect("upstream", "no_client_config")
        self._check_egress(meta.registration_endpoint, "registration_endpoint_denied")
        request = {
            "client_name": client_name,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        async with self._client_factory() as client:
            response = await client.post(meta.registration_endpoint, json=request)
        if response.status_code not in (200, 201):
            raise NeedsConnect("upstream", f"registration_refused_{response.status_code}")
        payload = response.json()
        return UpstreamClientRegistration(
            client_id=payload["client_id"], client_secret=payload.get("client_secret")
        )

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
        # SEC-1: the secret goes only where the egress policy allows
        self._check_egress(meta.token_endpoint, "token_endpoint_denied")
        if client_secret:
            data["client_secret"] = client_secret
        async with self._client_factory() as client:
            response = await client.post(meta.token_endpoint, data=data)
            response.raise_for_status()
            payload = response.json()
        return UpstreamTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
        )

    def _check_egress(self, url: str, reason: str) -> None:
        try:
            check_url_allowed(url, self._settings)
        except EgressDenied as exc:
            raise NeedsConnect("upstream", reason) from exc
