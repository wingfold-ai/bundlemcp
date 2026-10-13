"""Resolving the credentials a request carries: API keys and endpoint access tokens."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher
from bundlemcp.domain.shared.secrets import ACCESS_TOKEN_PREFIX, API_KEY_PREFIX

# Coarsen last_used_at writes: skip the UPDATE unless the key has been idle
# this long, so a busy key isn't written on every request.
_LAST_USED_REFRESH_SECONDS = 60


class AuthService:
    def __init__(self, uow: UnitOfWork, *, clock: Clock, hasher: SecretHasher) -> None:
        self._uow = uow
        self._clock = clock
        self._hasher = hasher
        self._keys = uow.api_keys
        self._tokens = uow.oauth_tokens
        self._users = uow.users

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
        # last_used_at is coarsened, so a busy key is not a write per call
        """Look up an active key by hash and refresh its coarse last_used_at."""
        if raw_key is None:
            return None
        key = await self._keys.by_hash(self._hasher.digest(raw_key))
        if key is None or not key.is_active:
            return None
        now = self._clock.now()
        if not key.used_within(_LAST_USED_REFRESH_SECONDS, now):
            key.last_used_at = now
            self._keys.add(key)
            await self._uow.commit()
        return key

    async def authenticate_api_key(
        self, *, authorization: str | None, x_api_key: str | None
    ) -> ApiKey | None:
        """Extract a key from request headers and resolve it in one step."""
        return await self.resolve_api_key(self.extract_key(authorization, x_api_key))

    async def authenticate_oauth_bearer(
        self, *, authorization: str | None, endpoint_id: uuid.UUID
    ) -> CallerIdentity | None:
        """Validate an endpoint access token against the database.

        Returns the user's identity, or None when the header carries no such token,
        the token is unknown, revoked or expired, its audience is a different
        endpoint, or its user is gone or deactivated.
        """
        if not authorization or not authorization.lower().startswith("bearer "):
            return None
        token = authorization[7:]
        if not token.startswith(ACCESS_TOKEN_PREFIX):
            return None
        row = await self._tokens.by_access_hash(self._hasher.digest(token))
        if row is None or not row.is_usable_at(self._clock.now()):
            return None
        if row.endpoint_id != endpoint_id:
            return None  # audience mismatch
        user = await self._users.get(row.user_id)
        if user is None or not user.is_active:
            return None
        return CallerIdentity.oauth_user(user)
