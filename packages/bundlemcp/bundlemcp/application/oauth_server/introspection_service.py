"""Answering a resource server that asks whether a token is good, and for whom."""

from bundlemcp.application.auth.auth_service import AuthService
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.delegation.delegated_token_issuer import DelegatedTokenIssuer
from bundlemcp.application.schemas import IntrospectionResponse
from bundlemcp.domain.access.caller_identity import API_KEY_SUBJECT_PREFIX
from bundlemcp.domain.delegation.delegated_token import DELEGATION_CLIENT_ID
from bundlemcp.domain.endpoints.endpoint_resource import EndpointResource
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_hasher import SecretHasher

INACTIVE = IntrospectionResponse(active=False)


class TokenIntrospectionService:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        auth: AuthService,
        clock: Clock,
        hasher: SecretHasher,
        public_base: str,
        delegated: DelegatedTokenIssuer | None = None,
    ) -> None:
        # delegated is None only where no delegated tokens are ever issued
        self._delegated = delegated
        self._auth = auth
        self._clock = clock
        self._hasher = hasher
        self._tokens = uow.oauth_tokens
        self._users = uow.users
        self._endpoints = uow.endpoints
        self._public_base = public_base

    async def introspect(self, token: str) -> IntrospectionResponse:
        if self._delegated is not None:
            delegated = await self._delegated.resolve(token)
            if delegated is not None:
                return IntrospectionResponse(
                    active=True,
                    sub=delegated.sub,
                    client_id=DELEGATION_CLIENT_ID,
                    exp=int(delegated.expires_at.timestamp()),
                    aud=delegated.audience,
                    email=delegated.email,
                    oidc_iss=delegated.oidc_issuer,
                    oidc_sub=delegated.oidc_sub,
                    token_use="delegated",
                    act={"sub": delegated.actor} if delegated.actor else None,
                )
        row = await self._tokens.by_access_hash(self._hasher.digest(token))
        if row is None:
            # forwarded bearers may be gateway API keys, not OAuth tokens —
            # report them with the `api_key:<id>` subject so introspecting
            # upstreams can serve api_key callers too.
            key = await self._auth.resolve_api_key(token)
            if key is None:
                return INACTIVE
            return IntrospectionResponse(
                active=True, sub=f"{API_KEY_SUBJECT_PREFIX}{key.id}", token_use="api_key"
            )
        if not row.is_usable_at(self._clock.now()):
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
            oidc_iss=user.oidc_issuer,
            oidc_sub=user.oidc_sub,
        )
