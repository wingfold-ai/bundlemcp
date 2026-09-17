import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher
from bundlemcp.domain.shared.secrets import ACCESS_TOKEN_PREFIX, REFRESH_TOKEN_PREFIX


class TokenIssuer:
    """Mints an access/refresh pair with the configured lifetimes and stores only their hashes."""

    def __init__(
        self,
        uow: UnitOfWork,
        policy: TokenPolicy,
        *,
        clock: Clock,
        generator: SecretGenerator,
        hasher: SecretHasher,
    ) -> None:
        self._tokens = uow.oauth_tokens
        self._policy = policy
        self._clock = clock
        self._generator = generator
        self._hasher = hasher

    def issue(
        self,
        *,
        client_id: str,
        user_id: uuid.UUID,
        endpoint_id: uuid.UUID,
        scope: str,
        family_id: uuid.UUID | None = None,
    ) -> TokenResponse:
        """Mint a pair; a refresh passes the family it continues, a fresh grant starts one."""
        access = ACCESS_TOKEN_PREFIX + self._generator.token(32)
        refresh = REFRESH_TOKEN_PREFIX + self._generator.token(32)
        now = self._clock.now()
        self._tokens.add(
            OAuthAccessToken(
                access_token_hash=self._hasher.digest(access),
                refresh_token_hash=self._hasher.digest(refresh),
                client_id=client_id,
                user_id=user_id,
                endpoint_id=endpoint_id,
                family_id=family_id or uuid.uuid4(),
                scope=scope,
                expires_at=now + self._policy.access_token_ttl,
                refresh_expires_at=now + self._policy.refresh_token_ttl,
            )
        )
        return TokenResponse(
            access_token=access,
            expires_in=int(self._policy.access_token_ttl.total_seconds()),
            refresh_token=refresh,
            scope=scope,
        )
