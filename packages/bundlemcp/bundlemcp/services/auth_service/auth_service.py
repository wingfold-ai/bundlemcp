from __future__ import annotations

import uuid
from datetime import UTC
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.crypto import ACCESS_TOKEN_PREFIX, API_KEY_PREFIX, hash_token
from bundlemcp.models import ApiKey, OAuthAccessToken, User, utcnow
from bundlemcp.services.auth_service.principal import Principal

if TYPE_CHECKING:
    from bundlemcp.oauth.adminsessions import AdminSessionStore

# Coarsen last_used_at writes: skip the UPDATE unless the key has been idle
# this long, so a busy key isn't written on every request (KEY-4).
_LAST_USED_REFRESH_SECONDS = 60


class AuthService:
    def __init__(
        self, db: AsyncSession, *, admin_sessions: AdminSessionStore | None = None
    ) -> None:
        self._db = db
        self._admin_sessions = admin_sessions

    @staticmethod
    def extract_key(authorization: str | None, x_api_key: str | None) -> str | None:
        """Pull an API key from Authorization: Bearer bmcp_sk_… or X-API-Key. Never query params."""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:]
            if token.startswith(API_KEY_PREFIX):
                return token
        if x_api_key and x_api_key.startswith(API_KEY_PREFIX):
            return x_api_key
        return None

    async def resolve_api_key(self, raw_key: str | None) -> ApiKey | None:
        """Look up an active key by hash and refresh its coarse last_used_at (KEY-4)."""
        if raw_key is None:
            return None
        result = await self._db.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_token(raw_key))
        )
        key = result.scalar_one_or_none()
        if key is None or not key.is_active:
            return None
        last = key.last_used_at  # sqlite returns naive datetimes — assume UTC
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is None or (utcnow() - last).total_seconds() > _LAST_USED_REFRESH_SECONDS:
            key.last_used_at = utcnow()
            await self._db.commit()
        return key

    async def authenticate_oauth_bearer(
        self, *, authorization: str | None, endpoint_id: uuid.UUID
    ) -> tuple[str, str | None] | None:
        """Validate an endpoint access token against the database.

        Returns (user_id, email), or None when the header carries no such token,
        the token is unknown, revoked or expired, its audience is a different
        endpoint, or its user is gone or deactivated.
        """
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        token = authorization[7:]
        if not token.startswith(ACCESS_TOKEN_PREFIX):
            return None
        row = (
            await self._db.execute(
                select(OAuthAccessToken).where(
                    OAuthAccessToken.access_token_hash == hash_token(token)
                )
            )
        ).scalar_one_or_none()
        if row is None or row.revoked:
            return None
        expires = row.expires_at  # sqlite returns naive datetimes — assume UTC
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < utcnow():
            return None
        if row.endpoint_id != endpoint_id:
            return None  # EP-3a: audience mismatch
        user = (
            await self._db.execute(select(User).where(User.id == row.user_id))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        return (str(user.id), user.email)

    def key_reaches_endpoint(self, key: ApiKey, endpoint_id: uuid.UUID) -> bool:
        """Whether a key may be used on this endpoint; unscoped keys reach all (KEY-2)."""
        if key.kind == "endpoint" and key.endpoint_ids:
            return str(endpoint_id) in key.endpoint_ids
        return True

    async def authenticate_api_key(
        self, *, authorization: str | None, x_api_key: str | None
    ) -> ApiKey | None:
        """Extract a key from request headers and resolve it in one step."""
        return await self.resolve_api_key(self.extract_key(authorization, x_api_key))

    async def session_user(self, session_id: str | None) -> User | None:
        """Resolve a browser session to its active user, admin or not.

        is_active/is_admin are re-checked against the DB so deactivation and
        demotion take effect immediately, not at session expiry.
        """
        if self._admin_sessions is None or not session_id:
            return None
        session = await self._admin_sessions.load(session_id)
        if session is None:
            return None
        
        user = (
            await self._db.execute(select(User).where(User.id == uuid.UUID(session.user_id)))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        return user

    async def admin_principal(self, session_id: str | None) -> Principal | None:
        """Resolve a browser session to an admin Principal.

        The caller still owns the CSRF origin check on mutating requests.
        """
        user = await self.session_user(session_id)
        if user is None or not user.is_admin:
            return None
        return Principal(kind="admin", user_id=str(user.id))
