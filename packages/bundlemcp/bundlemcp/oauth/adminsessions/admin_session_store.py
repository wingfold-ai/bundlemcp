import json
import secrets
from dataclasses import asdict

from redis.asyncio import Redis

from bundlemcp.oauth.adminsessions._common import ADMIN_SESSION_KEY, DEFAULT_MAX_AGE
from bundlemcp.oauth.adminsessions.admin_session import AdminSession


class AdminSessionStore:
    def __init__(self, redis: Redis, *, max_age: int = DEFAULT_MAX_AGE) -> None:
        self._redis = redis
        self.max_age = max_age

    def _key(self, session_id: str) -> str:
        return ADMIN_SESSION_KEY.format(session_id=session_id)

    async def create(self, session: AdminSession) -> str:
        session_id = secrets.token_urlsafe(32)
        await self._redis.set(self._key(session_id), json.dumps(asdict(session)), ex=self.max_age)
        return session_id

    async def load(self, session_id: str) -> AdminSession | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        return AdminSession(**json.loads(raw))

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))

    def cookie_kwargs(self, secure: bool) -> dict:
        """httpOnly, SameSite=Lax; Secure iff the public URL is https."""
        return {
            "httponly": True,
            "samesite": "lax",
            "secure": secure,
            "max_age": self.max_age,
            "path": "/",
        }
