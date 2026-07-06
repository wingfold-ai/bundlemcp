"""Authentication resolution shared by the management API, the MCP edge, and
the OAuth token endpoint.

Framework-free: methods take header/cookie strings and an AsyncSession, never a
web Request, so any edge can reuse them. HTTP status policy (401 vs 403) and
CSRF checks stay with the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bundlemcp.models import ApiKey, User, utcnow
from bundlemcp.security import API_KEY_PREFIX, hash_token

if TYPE_CHECKING:
    from bundlemcp.oauth.adminsessions import AdminSessionStore

# Coarsen last_used_at writes: skip the UPDATE unless the key has been idle
# this long, so a busy key isn't written on every request (KEY-4).
_LAST_USED_REFRESH_SECONDS = 60


@dataclass
class Principal:
    """The authenticated management-API caller: an admin user or a service key."""

    kind: str  # "admin" | "service"
    user_id: str | None = None
    api_key_id: str | None = None


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
        import uuid

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
