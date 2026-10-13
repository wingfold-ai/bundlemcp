"""The Authorization header an upstream server needs, resolved for one caller."""

from bundlemcp.application.delegation.delegated_token_issuer import DelegatedTokenIssuer
from bundlemcp.application.upstream_oauth.upstream_token_service import UpstreamTokenService
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_oauth_not_configured import UpstreamOAuthNotConfigured


class UpstreamCredentialResolver:
    """Turns a server's credential configuration into headers for one call.

    Servers without upstream OAuth or delegation need nothing beyond their
    static headers. Shared OAuth servers use the one connection an admin
    established; per-user servers use the calling user's own, so an anonymous
    caller can never reach one. A delegated-token server gets a token the
    gateway issues for the caller, valid only at that server.
    """

    def __init__(
        self,
        tokens: UpstreamTokenService | None,
        public_base: str,
        *,
        delegated: DelegatedTokenIssuer | None = None,
    ) -> None:
        # tokens is None exactly when no encryption keys are configured (the upstreams spec);
        # delegated is None only where no call is ever made on a caller's behalf
        self._tokens = tokens
        self._public_base = public_base
        self._delegated = delegated

    async def headers_for(
        self,
        server: McpServer,
        identity: CallerIdentity,
        *,
        endpoint: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, str]:
        if server.uses_delegated_token:
            token = (
                await self._delegated.issue(server, identity, endpoint=endpoint)
                if self._delegated is not None
                else None
            )
            return {"Authorization": f"Bearer {token}"} if token is not None else {}
        if not server.uses_upstream_oauth:
            return {}
        if self._tokens is None:
            raise UpstreamOAuthNotConfigured(server.name)
        user = None
        if server.is_per_user:
            user = identity.user_uuid
            if user is None:  # a per-user upstream without a user: should be unreachable
                raise NeedsConnect(server.name, "per_user_requires_user")
        access = await self._tokens.ensure_access_token(server, user, force=force_refresh)
        return {"Authorization": f"Bearer {access}"}

    async def discovery_headers(self, server: McpServer) -> dict[str, str]:
        """The Authorization header for listing a server's tools with no caller present.

        Raises NeedsConnect when no account is connected to borrow, and
        UpstreamOAuthNotConfigured when tokens cannot be stored at all.
        """
        if not server.uses_upstream_oauth:
            return {}
        if self._tokens is None:
            raise UpstreamOAuthNotConfigured(server.name)
        return {"Authorization": f"Bearer {await self._tokens.discovery_access_token(server)}"}

    async def needs_account(self, server: McpServer, identity: CallerIdentity) -> bool:
        """Whether this caller must connect their own account before using the server.

        Only a signed-in user can: their connection is keyed by their user,
        which an API-key or anonymous caller does not have.
        """
        if not server.requires_per_user_token or self._tokens is None:
            return False
        user = identity.user_uuid
        if user is None:
            return False
        return not await self._tokens.is_connected(server.id, user)

    async def request_step_up(self, server: McpServer, scopes: list[str]) -> None:
        """Have the server's next connect request scopes it demanded."""
        if self._tokens is not None and scopes:
            await self._tokens.request_step_up(server, scopes)

    def connect_url(self, server: McpServer) -> str:
        """Where the caller connects their account to the server."""
        suffix = "?as=me" if server.is_per_user else ""
        return f"{self._public_base}/oauth/upstream/{server.name}/connect{suffix}"

    def connect_hint(self, server: McpServer) -> str:
        """The message a caller sees when the upstream account still has to be connected."""
        return f"upstream not connected — connect at {self.connect_url(server)}"
