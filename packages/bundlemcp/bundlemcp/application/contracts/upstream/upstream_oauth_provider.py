from typing import Protocol, runtime_checkable

from bundlemcp.domain.upstream_oauth.upstream_client_registration import (
    UpstreamClientRegistration,
)
from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens


@runtime_checkable
class UpstreamOAuthProvider(Protocol):
    async def discover(self, server_url: str) -> UpstreamMetadata:
        """Follow the server's authorization chain to its authorization server's metadata.

        Raises ``NeedsConnect`` with reason ``no_oauth_metadata`` when the server
        publishes no OAuth metadata at all, and with another reason when the
        chain is refused (egress policy, issuer mismatch, no PKCE).
        """
        ...

    async def register(
        self, meta: UpstreamMetadata, *, redirect_uri: str, client_name: str
    ) -> UpstreamClientRegistration:
        """Register this gateway as a public web client at the server's registration endpoint."""
        ...

    def authorize_url(
        self,
        meta: UpstreamMetadata,
        *,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        scope: str | None,
    ) -> str: ...

    async def exchange(
        self,
        meta: UpstreamMetadata,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        client_id: str,
        client_secret: str | None,
    ) -> UpstreamTokens: ...

    async def refresh(
        self,
        meta: UpstreamMetadata,
        *,
        refresh_token: str,
        client_id: str,
        client_secret: str | None,
    ) -> UpstreamTokens: ...

    async def client_credentials(
        self,
        meta: UpstreamMetadata,
        *,
        client_id: str,
        client_secret: str,
        scope: str | None,
    ) -> UpstreamTokens:
        """Obtain a token for the gateway itself with the client credentials grant."""
        ...
