import secrets

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from bundlemcp.store.admin_sessions.admin_session import AdminSession

log = structlog.get_logger(__name__)

ADMIN_SESSION_KEY = "bmcp:adminsession:{session_id}"
DEFAULT_MAX_AGE = 12 * 3600  # seconds; forces re-login (ADM-6)


class AdminSessionStore:
    """Browser sessions for the management UI, kept in Valkey under random ids."""

    def __init__(self, redis: Redis, *, max_age: int = DEFAULT_MAX_AGE) -> None:
        self._redis = redis
        self.max_age = max_age

    def _key(self, session_id: str) -> str:
        return ADMIN_SESSION_KEY.format(session_id=session_id)

    async def create(self, session: AdminSession) -> str:
        session_id = secrets.token_urlsafe(32)
        await self._redis.set(self._key(session_id), session.model_dump_json(), ex=self.max_age)
        return session_id

    async def load(self, session_id: str) -> AdminSession | None:
        raw = await self._redis.get(self._key(session_id))
        if raw is None:
            return None
        # A stored record that no longer matches the schema is treated as no
        # session, so a rollout that changes the shape logs people out rather
        # than raising mid-request.
        try:
            return AdminSession.model_validate_json(raw)
        except ValidationError:
            log.warning("adminsession.malformed", session_id=session_id)
            return None

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))
