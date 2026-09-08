"""Keeping an upstream access token fresh, with one refresh at a time per connection."""

import asyncio
import uuid
from datetime import timedelta

import structlog

from bundlemcp.application.contracts.live_state.refresh_lock import RefreshLock
from bundlemcp.application.contracts.upstream.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.application.upstream_oauth.upstream_connect_flow import UpstreamConnectFlow
from bundlemcp.application.upstream_oauth.upstream_token_storage import UpstreamTokenStorage
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.upstream_oauth.needs_connect import NeedsConnect
from bundlemcp.domain.upstream_oauth.upstream_tokens import UpstreamTokens

log = structlog.get_logger(__name__)

REFRESH_LOCK_KEY = "bmcp:upstream-refresh:{server_id}:{user_key}"
REFRESH_SKEW = timedelta(seconds=60)  # refresh this long before actual expiry
REFRESH_LOCK_TTL = 30  # seconds
WAIT_ATTEMPTS = 50
WAIT_INTERVAL = 0.1


class UpstreamTokenRefresher:
    def __init__(
        self,
        tokens: UpstreamTokenStorage,
        flow: UpstreamConnectFlow,
        provider: UpstreamOAuthProvider,
        lock: RefreshLock,
    ) -> None:
        self._tokens = tokens
        self._flow = flow
        self._provider = provider
        self._lock = lock

    async def access_token(
        self, server: McpServer, user_id: uuid.UUID | None, *, force: bool = False
    ) -> str:
        """A valid access token, refreshed proactively when near expiry or when forced."""
        row = await self._tokens.load(server.id, user_id)
        if row is None or not row.is_valid:
            raise NeedsConnect(server.name)
        tokens = self._tokens.decode(row)
        if not force and not row.expires_within(REFRESH_SKEW):
            return tokens.access_token  # still fresh
        return await self._refresh_single_flight(server, user_id, tokens)

    async def _refresh_single_flight(
        self, server: McpServer, user_id: uuid.UUID | None, tokens: UpstreamTokens
    ) -> str:
        # UPO-4: concurrent callers cause exactly one refresh
        user_key = str(user_id) if user_id is not None else "shared"
        lock_key = REFRESH_LOCK_KEY.format(server_id=server.id, user_key=user_key)
        if not await self._lock.acquire(lock_key, ttl_seconds=REFRESH_LOCK_TTL):
            return await self._wait_for_other_refresh(server, user_id)
        try:
            return await self._refresh(server, user_id, tokens)
        finally:
            await self._lock.release(lock_key)

    async def _wait_for_other_refresh(self, server: McpServer, user_id: uuid.UUID | None) -> str:
        for _ in range(WAIT_ATTEMPTS):
            await asyncio.sleep(WAIT_INTERVAL)
            row = await self._tokens.load(server.id, user_id)
            if row is None or not row.is_valid:
                raise NeedsConnect(server.name, "refresh_failed")
            if not row.expires_within(REFRESH_SKEW):
                return self._tokens.decode(row).access_token
        raise NeedsConnect(server.name, "refresh_timeout")

    async def _refresh(
        self, server: McpServer, user_id: uuid.UUID | None, tokens: UpstreamTokens
    ) -> str:
        if not tokens.refresh_token:
            await self._tokens.invalidate(server.id, user_id)
            raise NeedsConnect(server.name, "no_refresh_token")
        config = await self._tokens.client_config(server.id)
        meta = await self._flow.metadata(server)
        try:
            refreshed = await self._provider.refresh(
                meta,
                refresh_token=tokens.refresh_token,
                client_id=config.client_id,
                client_secret=config.client_secret,
            )
        except Exception:
            log.warning("upstream_oauth.refresh_failed", server=server.name)
            await self._tokens.invalidate(server.id, user_id)
            raise NeedsConnect(server.name, "refresh_failed") from None
        if not refreshed.refresh_token:  # carry the old one forward if the provider didn't rotate
            refreshed = refreshed.model_copy(update={"refresh_token": tokens.refresh_token})
        await self._tokens.save(server.id, user_id, refreshed)
        return refreshed.access_token
