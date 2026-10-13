from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.oauth_server.pending_authorization import PendingAuthorization
from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.shared.clock import Clock
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher


class AuthorizationCodeIssuer:
    """Mints a single-use authorization code with the configured lifetime; stores only its hash."""

    def __init__(
        self,
        uow: UnitOfWork,
        policy: TokenPolicy,
        *,
        clock: Clock,
        generator: SecretGenerator,
        hasher: SecretHasher,
    ) -> None:
        self._codes = uow.authorization_codes
        self._policy = policy
        self._clock = clock
        self._generator = generator
        self._hasher = hasher

    def issue(self, pending: PendingAuthorization) -> str:
        """Stage a code bound to the approved request and return its raw value."""
        raw_code = self._generator.token(32)
        self._codes.add(
            OAuthAuthorizationCode(
                code_hash=self._hasher.digest(raw_code),
                client_id=pending.client_id,
                user_id=pending.user_id,
                endpoint_id=pending.endpoint_id,
                redirect_uri=pending.redirect_uri,
                scope=pending.scope,
                code_challenge=pending.code_challenge,
                code_challenge_method=CodeChallengeMethod.S256,
                expires_at=self._clock.now() + self._policy.authorization_code_ttl,  # AUTH-3
            )
        )
        return raw_code
