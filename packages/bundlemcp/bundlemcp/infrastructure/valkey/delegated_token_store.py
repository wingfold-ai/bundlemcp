"""Delegated upstream tokens, kept in Valkey until they expire."""

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from bundlemcp.domain.delegation.delegated_token import DelegatedToken

log = structlog.get_logger(__name__)

DELEGATED_TOKEN_KEY = "bmcp:delegated:{token_hash}"


class ValkeyDelegatedTokenStore:
    """Records keyed by the token's hash, expiring with the token, shared by every replica."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def put(self, token_hash: str, token: DelegatedToken, *, ttl_seconds: int) -> None:
        key = DELEGATED_TOKEN_KEY.format(token_hash=token_hash)
        await self._redis.set(key, token.model_dump_json(), ex=ttl_seconds)

    async def get(self, token_hash: str) -> DelegatedToken | None:
        raw = await self._redis.get(DELEGATED_TOKEN_KEY.format(token_hash=token_hash))
        if raw is None:
            return None
        try:
            return DelegatedToken.model_validate_json(raw)
        except ValidationError:
            log.warning("delegated_token.malformed")
            return None
