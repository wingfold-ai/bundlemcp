"""bundlemcp as an OAuth *client* to protected upstream MCP servers.

Discovery + pre-registered client, encrypted per-(server,user) token storage,
and proactive-expiry refresh with a Redis single-flight lock.
The IdP interaction is behind UpstreamOAuthProvider so hermetic tests inject a
fake instead of reaching a real authorization server.
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
    """No usable token for (server, user); the caller must (re)connect."""

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


class HttpxUpstreamProvider:
    """Real upstream IdP interaction via httpx (deployment path).

    Discovery follows the RFC 9728 → RFC 8414 chain from the server's origin;
    the auth-code flow uses PKCE. Injected fakes replace this in tests.
    """

    def __init__(self, settings) -> None:
        self._settings = settings

    async def discover(self, server_url: str) -> UpstreamMetadata:
        from urllib.parse import urlparse

        import httpx

        origin = "{0.scheme}://{0.netloc}".format(urlparse(server_url))
        async with httpx.AsyncClient(timeout=10) as client:
            # try protected-resource metadata first, else AS metadata at the origin
            for path in (
                "/.well-known/oauth-protected-resource",
                "/.well-known/oauth-authorization-server",
            ):
                resp = await client.get(origin + path)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if "authorization_servers" in data:  # protected-resource doc
                    as_url = data["authorization_servers"][0].rstrip("/")
                    resp = await client.get(as_url + "/.well-known/oauth-authorization-server")
                    resp.raise_for_status()
                    data = resp.json()
                return UpstreamMetadata(
                    authorization_endpoint=data["authorization_endpoint"],
                    token_endpoint=data["token_endpoint"],
                    registration_endpoint=data.get("registration_endpoint"),
                    scopes_supported=data.get("scopes_supported", []),
                )
        raise NeedsConnect("upstream", "no_oauth_metadata")

    def authorize_url(
        self, meta, *, client_id, redirect_uri, state, code_challenge, scope
    ) -> str:
        from urllib.parse import urlencode

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
        self, meta, *, code, redirect_uri, code_verifier, client_id, client_secret
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

    async def refresh(self, meta, *, refresh_token, client_id, client_secret) -> UpstreamTokens:
        return await self._token_request(
            meta,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            client_secret,
        )

    async def _token_request(self, meta, data: dict, client_secret: str | None) -> UpstreamTokens:
        import httpx

        if client_secret:
            data["client_secret"] = client_secret
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(meta.token_endpoint, data=data)
            resp.raise_for_status()
            payload = resp.json()
        return UpstreamTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
        )
