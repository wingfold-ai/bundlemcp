"""Answering a resource server that asks whether a token is good, and for whom."""

from bundlemcp.crypto import hash_token
from bundlemcp.models import API_KEY_SUBJECT_PREFIX, Endpoint, OAuthAccessToken, User
from bundlemcp.schemas import IntrospectionResponse
from bundlemcp.services.auth_service import AuthService
from bundlemcp.store import Repository, UnitOfWork

INACTIVE = IntrospectionResponse(active=False)


class TokenIntrospectionService:
    def __init__(self, uow: UnitOfWork, *, public_base: str) -> None:
        self._auth = AuthService(uow.session)
        self._tokens = Repository(uow.session, OAuthAccessToken)
        self._users = Repository(uow.session, User)
        self._endpoints = Repository(uow.session, Endpoint)
        self._public_base = public_base

    async def introspect(self, token: str) -> IntrospectionResponse:
        row = await self._tokens.one(OAuthAccessToken.access_token_hash == hash_token(token))
        if row is None:
            # FWD-4: forwarded bearers may be gateway API keys, not OAuth tokens —
            # report them with the FWD-3 identity format so introspecting
            # upstreams can serve api_key callers too.
            key = await self._auth.resolve_api_key(token)
            if key is None:
                return INACTIVE
            return IntrospectionResponse(
                active=True, sub=f"{API_KEY_SUBJECT_PREFIX}{key.id}", token_use="api_key"
            )
        if not row.is_usable:
            return INACTIVE
        user = await self._users.get(row.user_id)
        if user is None or not user.is_active:
            return INACTIVE
        endpoint = await self._endpoints.get(row.endpoint_id)
        return IntrospectionResponse(
            active=True,
            sub=str(row.user_id),
            client_id=row.client_id,
            scope=row.scope,
            exp=int(row.expires_at.timestamp()),
            aud=f"{self._public_base}/{endpoint.name}/mcp" if endpoint else None,
            email=user.email,
        )
