"""Everything the gateway needs from a server's upstream OAuth, behind one door."""

import uuid

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.contracts.secret_cipher import SecretCipher
from bundlemcp.application.contracts.upstream.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.application.schemas import UpstreamConnectionStatus
from bundlemcp.application.upstream_oauth.authorize_start import AuthorizeStart
from bundlemcp.application.upstream_oauth.upstream_connect_flow import UpstreamConnectFlow
from bundlemcp.application.upstream_oauth.upstream_token_refresher import UpstreamTokenRefresher
from bundlemcp.application.upstream_oauth.upstream_token_storage import UpstreamTokenStorage
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens


class UpstreamTokenService:
    """Facade over storage, the connect flow and refresh for upstream OAuth tokens.

    Persistence, the interactive connect and the single-flight refresh are three
    jobs with three classes; this object composes them so callers hold one.
    """

    def __init__(
        self,
        units: UnitOfWorkFactory,
        cipher: SecretCipher,
        lock: RefreshLock,
        provider: UpstreamOAuthProvider,
    ) -> None:
        self._tokens = UpstreamTokenStorage(units, cipher)
        self._flow = UpstreamConnectFlow(self._tokens, provider)
        self._refresher = UpstreamTokenRefresher(self._tokens, self._flow, provider, lock)

    @property
    def configured(self) -> bool:
        return True

    async def save(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None, tokens: UpstreamTokens
    ) -> None:
        await self._tokens.save(server_id, user_id, tokens)

    async def status(
        self, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamConnectionStatus:
        """Connection status only — never token values."""
        row = await self._tokens.load(server_id, user_id)
        if row is None:
            return UpstreamConnectionStatus()
        return UpstreamConnectionStatus(
            connected=row.is_connected,
            valid=row.is_valid,
            expires_at=row.expires_at,
            account_hint=row.account_hint,
        )

    async def disconnect(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        await self._tokens.delete(server_id, user_id)

    async def build_authorize(
        self, server: McpServer, redirect_uri: str, state: str
    ) -> AuthorizeStart:
        return await self._flow.begin(server, redirect_uri, state)

    async def complete_authorize(
        self,
        server: McpServer,
        user_id: uuid.UUID | None,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> None:
        await self._flow.complete(
            server, user_id, code=code, code_verifier=code_verifier, redirect_uri=redirect_uri
        )

    async def ensure_access_token(
        self, server: McpServer, user_id: uuid.UUID | None, *, force: bool = False
    ) -> str:
        """A valid access token, refreshing proactively if near expiry.

        `force=True` refreshes regardless of expiry — the reactive path used
        after an upstream rejection despite a non-expired token.
        """
        return await self._refresher.access_token(server, user_id, force=force)
