import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.oauth.pkce import pkce_verifies


class OAuthAuthorizationCode(BaseModel):
    code_hash: str = Field(description="Hash of the code; the code itself is never stored")
    client_id: str = Field(
        description="Client the code was issued to",
    )
    user_id: uuid.UUID = Field(
        description="User who authorized it",
    )
    endpoint_id: uuid.UUID = Field(
        description="Endpoint the resulting token will be valid for",
    )
    redirect_uri: str = Field(
        description="Redirect URI used, which the token exchange must repeat exactly"
    )
    scope: str = Field(default="mcp", description="Scopes the code will grant")
    code_challenge: str = Field(description="PKCE challenge the exchange must satisfy")
    code_challenge_method: CodeChallengeMethod = Field(
        default=CodeChallengeMethod.S256,
        description="How the challenge was derived; only S256 is accepted",
    )
    expires_at: datetime = Field(description="When the code expires")
    used: bool = Field(
        default=False,
        description="Whether the code has been redeemed. A code works exactly once",
    )

    def is_redeemable_at(self, now: datetime) -> bool:
        """Unused and not yet expired, so it may still be exchanged for tokens."""
        return not self.used and self.expires_at >= now

    def issued_to(self, client_id: str) -> bool:
        """Whether this client is the one the code was issued to; no other may redeem it."""
        return self.client_id == client_id

    def sent_to(self, redirect_uri: str | None) -> bool:
        """Whether the exchange repeats the redirect URI the code was delivered to."""
        return redirect_uri == self.redirect_uri

    def proves_possession(self, code_verifier: str) -> bool:
        """Whether the verifier matches the challenge the code was bound to (PKCE)."""
        # only S256 exists; a second method would dispatch on code_challenge_method here
        return pkce_verifies(code_verifier, self.code_challenge)
