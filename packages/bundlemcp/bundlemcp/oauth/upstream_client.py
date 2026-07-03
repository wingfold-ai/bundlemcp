"""bundlemcp as an OAuth *client* to protected upstream MCP servers (spec 23).

Discovery + pre-registered client, encrypted per-(server,user) token storage,
and proactive-expiry refresh with a Redis single-flight lock (UPO-1/2/4/5).
The IdP interaction is behind UpstreamOAuthProvider so hermetic tests inject a
fake instead of reaching a real authorization server (ARC-14).
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

import structlog
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from bundlemcp.crypto import TokenCipher
from bundlemcp.models import McpServer, UpstreamOAuthClient, UpstreamOAuthToken, utcnow

log = structlog.get_logger(__name__)

REFRESH_LOCK_KEY = "bmcp:upstream-refresh:{server_id}:{user_key}"
REFRESH_SKEW = timedelta(seconds=60)  # refresh this long before actual expiry
REFRESH_LOCK_TTL = 30  # seconds


class NeedsConnect(Exception):
    """No usable token for (server, user); the caller must (re)connect (UPO-3/4)."""

    def __init__(self, server_name: str, reason: str = "not_connected") -> None:
        self.server_name = server_name
        self.reason = reason
        super().__init__(f"{server_name}: {reason}")


class UpstreamMetadata(BaseModel):
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    scopes_supported: list[str] = []


class UpstreamTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None  # seconds
    scope: str | None = None
    account_hint: str | None = None  # e.g. masked account/email for UI (UPO-5)


class UpstreamOAuthProvider(Protocol):
    async def discover(self, server_url: str) -> UpstreamMetadata: ...

    def authorize_url(
        self, meta: UpstreamMetadata, *, client_id: str, redirect_uri: str,
        state: str, code_challenge: str, scope: str | None,
    ) -> str: ...

    async def exchange(
        self, meta: UpstreamMetadata, *, code: str, redirect_uri: str,
        code_verifier: str, client_id: str, client_secret: str | None,
    ) -> UpstreamTokens: ...

    async def refresh(
        self, meta: UpstreamMetadata, *, refresh_token: str,
        client_id: str, client_secret: str | None,
    ) -> UpstreamTokens: ...


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _user_key(user_id: uuid.UUID | None) -> str:
    return str(user_id) if user_id is not None else "shared"


class UpstreamTokenStore:
    """Encrypted token storage keyed (server_id, user_id); NULL user = shared (UPO-2/5)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: TokenCipher,
        redis: Redis,
        provider: UpstreamOAuthProvider,
    ) -> None:
        self._sessions = session_factory
        self._cipher = cipher
        self._redis = redis
        self._provider = provider

    async def save(
        self,
        server_id: uuid.UUID,
        user_id: uuid.UUID | None,
        tokens: UpstreamTokens,
    ) -> None:
        blob = self._cipher.encrypt(tokens.model_dump_json())
        expires_at = (
            utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
        )
        async with self._sessions() as db:
            row = await self._row(db, server_id, user_id)
            if row is None:
                row = UpstreamOAuthToken(
                    server_id=server_id, user_id=user_id, tokens_encrypted=blob
                )
            row.tokens_encrypted = blob
            row.expires_at = expires_at
            row.is_valid = True
            if tokens.account_hint:
                row.account_hint = tokens.account_hint
            db.add(row)
            await db.commit()

    async def status(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> dict:
        """UPO-5: connection status only — never token values."""
        async with self._sessions() as db:
            row = await self._row(db, server_id, user_id)
        if row is None:
            return {"connected": False}
        expires = _aware(row.expires_at)
        expired = expires is not None and expires < utcnow()
        return {
            "connected": row.is_valid and not expired,
            "expires_at": expires.isoformat() if expires else None,
            "account_hint": row.account_hint,
            "valid": row.is_valid,
        }

    async def disconnect(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        async with self._sessions() as db:
            row = await self._row(db, server_id, user_id)
            if row is not None:
                await db.delete(row)
                await db.commit()

    async def ensure_access_token(
        self, server: McpServer, user_id: uuid.UUID | None
    ) -> str:
        """Return a valid access token, refreshing proactively if near expiry (UPO-4)."""
        async with self._sessions() as db:
            row = await self._row(db, server.id, user_id)
            if row is None or not row.is_valid:
                raise NeedsConnect(server.name)
            tokens = self._decode(row)
            expires = _aware(row.expires_at)

        if expires is None or expires - REFRESH_SKEW > utcnow():
            return tokens.access_token  # still fresh

        # near/at expiry -> refresh under a single-flight lock (UPO-4)
        return await self._refresh_locked(server, user_id, tokens)

    # --- internals ---

    async def _refresh_locked(
        self, server: McpServer, user_id: uuid.UUID | None, tokens: UpstreamTokens
    ) -> str:
        lock_key = REFRESH_LOCK_KEY.format(server_id=server.id, user_key=_user_key(user_id))
        got_lock = await self._redis.set(lock_key, "1", nx=True, ex=REFRESH_LOCK_TTL)
        if not got_lock:
            # someone else is refreshing; wait briefly then re-read
            import asyncio

            for _ in range(50):
                await asyncio.sleep(0.1)
                async with self._sessions() as db:
                    row = await self._row(db, server.id, user_id)
                if row is None or not row.is_valid:
                    raise NeedsConnect(server.name, "refresh_failed")
                expires = _aware(row.expires_at)
                if expires is None or expires - REFRESH_SKEW > utcnow():
                    return self._decode(row).access_token
            raise NeedsConnect(server.name, "refresh_timeout")

        try:
            if not tokens.refresh_token:
                await self._invalidate(server.id, user_id)
                raise NeedsConnect(server.name, "no_refresh_token")
            client = await self._client_config(server.id)
            meta = await self._metadata(server)
            try:
                new_tokens = await self._provider.refresh(
                    meta,
                    refresh_token=tokens.refresh_token,
                    client_id=client["client_id"],
                    client_secret=client["client_secret"],
                )
            except Exception:
                log.warning("upstream_oauth.refresh_failed", server=server.name)
                await self._invalidate(server.id, user_id)
                raise NeedsConnect(server.name, "refresh_failed") from None
            # carry the old refresh token forward if the provider didn't rotate it
            if not new_tokens.refresh_token:
                new_tokens.refresh_token = tokens.refresh_token
            await self.save(server.id, user_id, new_tokens)
            return new_tokens.access_token
        finally:
            await self._redis.delete(lock_key)

    async def _invalidate(self, server_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
        async with self._sessions() as db:
            row = await self._row(db, server_id, user_id)
            if row is not None:
                row.is_valid = False
                db.add(row)
                await db.commit()

    def _decode(self, row: UpstreamOAuthToken) -> UpstreamTokens:
        return UpstreamTokens(**json.loads(self._cipher.decrypt(row.tokens_encrypted)))

    async def _row(
        self, db: AsyncSession, server_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> UpstreamOAuthToken | None:
        stmt = select(UpstreamOAuthToken).where(UpstreamOAuthToken.server_id == server_id)
        stmt = stmt.where(
            UpstreamOAuthToken.user_id.is_(None)  # type: ignore[union-attr]
            if user_id is None
            else UpstreamOAuthToken.user_id == user_id
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _client_config(self, server_id: uuid.UUID) -> dict:
        async with self._sessions() as db:
            client = (
                await db.execute(
                    select(UpstreamOAuthClient).where(UpstreamOAuthClient.server_id == server_id)
                )
            ).scalar_one_or_none()
        if client is None or not client.client_id:
            raise NeedsConnect("server", "no_client_config")
        secret = (
            self._cipher.decrypt(client.client_secret_encrypted)
            if client.client_secret_encrypted
            else None
        )
        return {
            "client_id": client.client_id,
            "client_secret": secret,
            "metadata": client.metadata_,
        }

    async def _metadata(self, server: McpServer) -> UpstreamMetadata:
        cfg = await self._client_config(server.id)
        cached = cfg.get("metadata") or {}
        if cached.get("authorization_endpoint") and cached.get("token_endpoint"):
            return UpstreamMetadata(**cached)
        return await self._provider.discover(server.url)
