import uuid
from datetime import timedelta

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.schemas import TokenResponse
from bundlemcp.domain.oauth.oauth_access_token import OAuthAccessToken
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import (
    ACCESS_TOKEN_PREFIX,
    REFRESH_TOKEN_PREFIX,
    generate_token,
    hash_token,
)

ACCESS_TOKEN_TTL = timedelta(hours=1)  # OAS-4
REFRESH_TOKEN_TTL = timedelta(days=7)


class TokenIssuer:
    """Mints an access/refresh pair and stores only their hashes."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._tokens = uow.oauth_tokens

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
        access = generate_token(ACCESS_TOKEN_PREFIX)
        refresh = generate_token(REFRESH_TOKEN_PREFIX)
        self._tokens.add(
            OAuthAccessToken(
                access_token_hash=hash_token(access),
                refresh_token_hash=hash_token(refresh),
                client_id=client_id,
                user_id=user_id,
                endpoint_id=endpoint_id,
                family_id=family_id or uuid.uuid4(),
                scope=scope,
                expires_at=utcnow() + ACCESS_TOKEN_TTL,
                refresh_expires_at=utcnow() + REFRESH_TOKEN_TTL,
            )
        )
        return TokenResponse(
            access_token=access,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
            refresh_token=refresh,
            scope=scope,
        )
