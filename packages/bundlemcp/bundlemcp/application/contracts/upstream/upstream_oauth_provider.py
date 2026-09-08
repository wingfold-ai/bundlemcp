from typing import Protocol, runtime_checkable

from bundlemcp.domain.upstream_oauth.upstream_metadata import UpstreamMetadata
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens


@runtime_checkable
class UpstreamOAuthProvider(Protocol):
    async def discover(self, server_url: str) -> UpstreamMetadata: ...

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
