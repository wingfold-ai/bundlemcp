"""The Authorization header an upstream server needs, resolved for one caller."""

from bundlemcp.models import CallerIdentity, McpServer
from bundlemcp.oauth.upstream_client import (
    NeedsConnect,
    UpstreamOAuthNotConfigured,
    UpstreamTokenStore,
)


class UpstreamCredentialResolver:
    """Turns a server's upstream OAuth configuration into headers for one call.

    Servers without upstream OAuth need nothing. Shared servers use the one
    connection an admin established; per-user servers use the calling user's
    own, so an anonymous caller can never reach one.
    """

    def __init__(self, tokens: UpstreamTokenStore | None, public_base: str) -> None:
        # tokens is None exactly when no encryption keys are configured (spec 23)
        self._tokens = tokens
        self._public_base = public_base

    async def headers_for(
        self, server: McpServer, identity: CallerIdentity, *, force_refresh: bool = False
    ) -> dict[str, str]:
        if not server.uses_upstream_oauth:
            return {}
        if self._tokens is None:
            raise UpstreamOAuthNotConfigured(server.name)
        user = None
        if server.is_per_user:
            user = identity.user_uuid
            if user is None:  # UPO-6 guard (should be unreachable)
                raise NeedsConnect(server.name, "per_user_requires_user")
        access = await self._tokens.ensure_access_token(server, user, force=force_refresh)
        return {"Authorization": f"Bearer {access}"}

    def connect_hint(self, server: McpServer) -> str:
        """The message a caller sees when the upstream account still has to be connected."""
        suffix = "?as=me" if server.is_per_user else ""
        return (
            "upstream not connected — connect at "
            f"{self._public_base}/oauth/upstream/{server.name}/connect{suffix}"
        )
