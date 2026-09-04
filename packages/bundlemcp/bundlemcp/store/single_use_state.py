"""State that must survive one round trip through the browser and then vanish."""

import secrets

import structlog
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

log = structlog.get_logger(__name__)


class SingleUseState[T: BaseModel]:
    """A typed record parked in Valkey under an unguessable token, readable exactly once.

    Used wherever a flow leaves the gateway and comes back: the token travels
    in a redirect or a form and proves the return belongs to the departure.
    Reading deletes, so a replayed token finds nothing.
    """

    def __init__(self, redis: Redis, *, prefix: str, ttl_seconds: int, model: type[T]) -> None:
        self._redis = redis
        self._prefix = prefix
        self._ttl = ttl_seconds
        self._model = model

    def _key(self, token: str) -> str:
        return f"{self._prefix}:{token}"

    async def put(self, value: T, *, token: str | None = None) -> str:
        """Store the record and return the token that retrieves it.

        A caller that already handed a token to a third party (an OAuth ``state``)
        passes it in; otherwise an unguessable one is generated.
        """
        token = token or secrets.token_urlsafe(32)
        await self._redis.set(self._key(token), value.model_dump_json(), ex=self._ttl)
        return token

    async def take(self, token: str) -> T | None:
        """Retrieve and delete; None when unknown, expired, already taken or malformed."""
        key = self._key(token)
        raw = await self._redis.get(key)
        await self._redis.delete(key)
        if raw is None:
            return None
        try:
            return self._model.model_validate_json(raw)
        except ValidationError:
            log.warning("single_use_state.malformed", prefix=self._prefix)
            return None
