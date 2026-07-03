"""Browser sessions for humans: random id in Redis, httpOnly cookie.

Max age forces periodic re-login so IdP-side changes take effect.
"""

import json
import secrets
from dataclasses import asdict, dataclass

from redis.asyncio import Redis

SESSION_COOKIE = "bmcp_session"
ADMIN_SESSION_KEY = "bmcp:adminsession:{session_id}"
DEFAULT_MAX_AGE = 12 * 3600  # seconds; forces re-login (ADM-6)


@dataclass
class AdminSession:
    user_id: str
    email: str | None
    is_admin: bool


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
