"""Answering a resource server that asks whether a token is good, and for whom."""

from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.schemas import IntrospectionResponse
from bundlemcp.domain.access.caller_identity import API_KEY_SUBJECT_PREFIX
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource
from bundlemcp.domain.shared.secrets import hash_token

INACTIVE = IntrospectionResponse(active=False)


class TokenIntrospectionService:
    def __init__(self, uow: UnitOfWork, *, public_base: str) -> None:
        self._auth = AuthService(uow)
        self._tokens = uow.oauth_tokens
        self._users = uow.users
        self._endpoints = uow.endpoints
        self._public_base = public_base

    async def introspect(self, token: str) -> IntrospectionResponse:
        row = await self._tokens.by_access_hash(hash_token(token))
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
        audience = (
            EndpointResource(public_base=self._public_base, endpoint_name=endpoint.name).url
            if endpoint
            else None
        )
        return IntrospectionResponse(
            active=True,
            sub=str(row.user_id),
            client_id=row.client_id,
            scope=row.scope,
            exp=int(row.expires_at.timestamp()),
            aud=audience,
            email=user.email,
        )
