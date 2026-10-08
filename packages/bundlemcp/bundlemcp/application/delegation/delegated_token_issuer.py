"""Issuing and recognising the tokens the gateway hands upstreams on a caller's behalf."""

from datetime import timedelta

from bundlemcp.application.contracts.live_state.delegated_token_store import (
    DelegatedTokenStore,
)
from bundlemcp.domain.access.caller_identity import CallerIdentity
from bundlemcp.domain.delegation.delegated_token import (
    DELEGATED_TOKEN_TTL_SECONDS,
    DelegatedToken,
)
from bundlemcp.domain.servers.mcp_server import McpServer
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher
from bundlemcp.domain.shared.secrets import DELEGATED_TOKEN_PREFIX


class DelegatedTokenIssuer:
    """Token exchange inside the gateway: caller identity in, upstream-bound token out.

    Every upstream request gets a freshly minted token, valid for five minutes
    and only at the one server it names as audience, so the upstream never
    sees a token that would also open the caller's endpoint.
    """

    def __init__(
        self,
        store: DelegatedTokenStore,
        *,
        clock: Clock,
        generator: SecretGenerator,
        hasher: SecretHasher,
    ) -> None:
        self._store = store
        self._clock = clock
        self._generator = generator
        self._hasher = hasher

    async def issue(
        self, server: McpServer, identity: CallerIdentity, *, endpoint: str | None
    ) -> str | None:
        """A token for this caller at this server; None for an anonymous caller."""
        sub = identity.sub
        if sub is None:
            return None
        value = DELEGATED_TOKEN_PREFIX + self._generator.token(32)
        record = DelegatedToken(
            sub=sub,
            email=identity.user_email,
            oidc_issuer=identity.oidc_issuer,
            oidc_sub=identity.oidc_sub,
            server_id=server.id,
            audience=server.url,
            endpoint=endpoint,
            expires_at=self._clock.now() + timedelta(seconds=DELEGATED_TOKEN_TTL_SECONDS),
        )
        await self._store.put(
            self._hasher.digest(value), record, ttl_seconds=DELEGATED_TOKEN_TTL_SECONDS
        )
        return value

    async def resolve(self, value: str) -> DelegatedToken | None:
        """The live record behind a presented token, or None."""
        if not value.startswith(DELEGATED_TOKEN_PREFIX):
            return None
        record = await self._store.get(self._hasher.digest(value))
        if record is None or not record.is_usable_at(self._clock.now()):
            return None
        return record
