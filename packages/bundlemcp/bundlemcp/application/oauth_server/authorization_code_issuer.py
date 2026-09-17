import secrets

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.oauth_server.pending_authorization import PendingAuthorization
from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.oauth.oauth_authorization_code import OAuthAuthorizationCode
from bundlemcp.domain.oauth.token_policy import TokenPolicy
from bundlemcp.domain.shared.clock import utcnow
from bundlemcp.domain.shared.secrets import hash_token


class AuthorizationCodeIssuer:
    """Mints a single-use authorization code with the configured lifetime; stores only its hash."""

    def __init__(self, uow: UnitOfWork, policy: TokenPolicy) -> None:
        self._codes = uow.authorization_codes
        self._policy = policy

    def issue(self, pending: PendingAuthorization) -> str:
        """Stage a code bound to the approved request and return its raw value."""
        raw_code = secrets.token_urlsafe(32)
        self._codes.add(
            OAuthAuthorizationCode(
                code_hash=hash_token(raw_code),
                client_id=pending.client_id,
                user_id=pending.user_id,
                endpoint_id=pending.endpoint_id,
                redirect_uri=pending.redirect_uri,
                scope=pending.scope,
                code_challenge=pending.code_challenge,
                code_challenge_method=CodeChallengeMethod.S256,
                expires_at=utcnow() + self._policy.authorization_code_ttl,  # OAS-3
            )
        )
        return raw_code
