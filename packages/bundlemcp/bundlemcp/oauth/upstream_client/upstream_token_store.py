import json
import uuid
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from bundlemcp.crypto import TokenCipher
from bundlemcp.models import McpServer, UpstreamOAuthClient, UpstreamOAuthToken, utcnow
from bundlemcp.oauth.upstream_client._common import (
    REFRESH_LOCK_KEY,
    REFRESH_LOCK_TTL,
    REFRESH_SKEW,
    _aware,
    _user_key,
    log,
)
from bundlemcp.oauth.upstream_client.needs_connect import NeedsConnect
from bundlemcp.oauth.upstream_client.upstream_metadata import UpstreamMetadata
from bundlemcp.oauth.upstream_client.upstream_oauth_provider import UpstreamOAuthProvider
from bundlemcp.oauth.upstream_client.upstream_tokens import UpstreamTokens


class UpstreamTokenStore:
    """Encrypted token storage keyed (server_id, user_id); NULL user = shared."""

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
        """Connection status only — never token values."""
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

    # --- interactive connect flow (UPO-1/3) ---

    async def build_authorize(
        self, server: McpServer, redirect_uri: str, state: str
    ) -> tuple[str, str]:
        """Return (authorize_url, code_verifier) for a PKCE S256 connect."""
        import base64
        import hashlib
        import secrets

        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        cfg = await self._client_config(server.id)
        meta = await self._metadata(server)
        scope = " ".join(meta.scopes_supported) if meta.scopes_supported else None
        url = self._provider.authorize_url(
            meta,
            client_id=cfg["client_id"],
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
            scope=scope,
        )
        return url, verifier

    async def complete_authorize(
        self,
        server: McpServer,
        user_id: uuid.UUID | None,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> None:
        cfg = await self._client_config(server.id)
        meta = await self._metadata(server)
        tokens = await self._provider.exchange(
            meta,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
        )
        await self.save(server.id, user_id, tokens)

    async def ensure_access_token(
        self, server: McpServer, user_id: uuid.UUID | None, *, force: bool = False
    ) -> str:
        """Return a valid access token, refreshing proactively if near expiry.

        `force=True` refreshes regardless of expiry — the reactive path used
        after an upstream 401 despite a non-expired token.
        """
        async with self._sessions() as db:
            row = await self._row(db, server.id, user_id)
            if row is None or not row.is_valid:
                raise NeedsConnect(server.name)
            tokens = self._decode(row)
            expires = _aware(row.expires_at)

        if not force and (expires is None or expires - REFRESH_SKEW > utcnow()):
            return tokens.access_token  # still fresh

        # near/at expiry (or forced) -> refresh under a single-flight lock (UPO-4)
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
