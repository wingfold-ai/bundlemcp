"""The real identity provider, reached over HTTP, its ID tokens verified with joserfc."""

from collections.abc import Callable
from functools import partial
from typing import Any, Self
from urllib.parse import urlencode

import httpx
import structlog
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from bundlemcp.application.settings.settings import Settings
from bundlemcp.domain.access.oidc_claims import OidcClaims
from bundlemcp.domain.access.oidc_error import OidcError
from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.infrastructure.egress.egress_policy import EgressDenied, check_url_allowed
from bundlemcp.infrastructure.httpx.guarded_client import guarded_client

HTTP_TIMEOUT = 10
ID_TOKEN_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256"]

ClientFactory = Callable[[], httpx.AsyncClient]

log = structlog.get_logger(__name__)


def _guarded(settings: Settings) -> ClientFactory:
    return partial(guarded_client, settings, timeout=HTTP_TIMEOUT)


class JoseOidcProvider:
    """A provider is built from its discovery document, so it is ready once constructed.

    Every URL it reaches — the discovery document, the token endpoint and the
    JWKS — passes the egress policy, so an issuer that resolves to a blocked
    range is refused rather than fetched.

    Logins carry a PKCE S256 challenge, which an issuer that does not enforce
    PKCE ignores. Only an issuer whose discovery document lists challenge
    methods without S256 is sent none, since it would refuse the request.
    """

    def __init__(
        self,
        settings: Settings,
        metadata: dict[str, Any],
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._settings = settings
        self._metadata = metadata
        self._client_factory = client_factory or _guarded(settings)
        self._sends_pkce = _accepts_s256(metadata)
        if not self._sends_pkce:
            log.warning(
                "oidc.pkce_unsupported",
                issuer=metadata.get("issuer"),
                code_challenge_methods_supported=metadata.get("code_challenge_methods_supported"),
            )

    @classmethod
    async def discover(
        cls, settings: Settings, *, client_factory: ClientFactory | None = None
    ) -> Self:
        """Fetch the issuer's discovery document and return a provider that can use it."""
        if not settings.oidc_discovery_url:
            raise OidcError("no OIDC discovery URL configured")
        _check_egress(settings.oidc_discovery_url, settings)
        client_factory = client_factory or _guarded(settings)
        try:
            async with client_factory() as client:
                response = await client.get(settings.oidc_discovery_url)
                response.raise_for_status()
                metadata = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError("OIDC discovery document could not be fetched") from exc
        if "issuer" not in metadata:
            raise OidcError("OIDC discovery document names no issuer")
        return cls(settings, metadata, client_factory=client_factory)

    async def authorize_url(
        self, *, state: str, nonce: str, redirect_uri: str, code_challenge: str
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self._settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        if self._sends_pkce:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = CodeChallengeMethod.S256
        return f"{self._metadata['authorization_endpoint']}?{urlencode(params)}"

    async def exchange(
        self, *, code: str, redirect_uri: str, nonce: str, code_verifier: str
    ) -> OidcClaims:
        token_endpoint = self._metadata["token_endpoint"]
        jwks_uri = self._metadata["jwks_uri"]
        _check_egress(token_endpoint, self._settings)
        _check_egress(jwks_uri, self._settings)
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._settings.oidc_client_id,
            "client_secret": self._settings.oidc_client_secret,
        }
        if self._sends_pkce:
            form["code_verifier"] = code_verifier
        try:
            async with self._client_factory() as client:
                token_response = await client.post(token_endpoint, data=form)
                token_response.raise_for_status()
                id_token = token_response.json()["id_token"]
                jwks_response = await client.get(jwks_uri)
                jwks_response.raise_for_status()
                jwks = jwks_response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise OidcError("identity provider token exchange failed") from exc
        claims = self._verify(id_token, jwks)
        if claims.get("nonce") != nonce:
            raise OidcError("nonce mismatch")
        return OidcClaims(
            issuer=claims["iss"],
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            groups=claims.get("groups", []),
        )

    def _verify(self, id_token: str, jwks: dict[str, Any]) -> dict[str, Any]:
        """Check the signature against the JWKS, then the claims OIDC Core requires.

        joserfc verifies only the signature; the registry is what binds the
        token to this issuer and this client and refuses an expired one.
        """
        registry = jwt.JWTClaimsRegistry(
            iss={"essential": True, "value": self._metadata["issuer"]},
            aud={"essential": True, "value": self._settings.oidc_client_id},
            exp={"essential": True},
            sub={"essential": True},
        )
        try:
            key_set = KeySet.import_key_set(jwks)
            token = jwt.decode(id_token, key_set, algorithms=ID_TOKEN_ALGORITHMS)
            registry.validate(token.claims)
        except (JoseError, ValueError) as exc:
            raise OidcError("ID token rejected") from exc
        return token.claims


def _accepts_s256(metadata: dict[str, Any]) -> bool:
    """Whether the issuer takes an S256 challenge; one that lists no methods is assumed to."""
    methods = metadata.get("code_challenge_methods_supported")
    return methods is None or CodeChallengeMethod.S256 in methods


def _check_egress(url: str, settings: Settings) -> None:
    try:
        check_url_allowed(url, settings)
    except EgressDenied as exc:
        raise OidcError("identity provider URL is not allowed by the egress policy") from exc
