import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from bundlemcp.domain.oauth.code_challenge_method import CodeChallengeMethod
from bundlemcp.domain.shared.clock import utcnow


class OAuthAuthorizationCode(BaseModel):
    code_hash: str = Field(  # OAS-8
        description="Hash of the code; the code itself is never stored"
    )
    client_id: str = Field(
        description="Client the code was issued to",
    )
    user_id: uuid.UUID = Field(
        description="User who authorized it",
    )
    endpoint_id: uuid.UUID = Field(  # OAS-10
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
    used: bool = Field(  # OAS-3
        default=False,
        description="Whether the code has been redeemed. A code works exactly once",
    )

    @property
    def is_redeemable(self) -> bool:
        """Unused and not yet expired, so it may still be exchanged for tokens."""
        return not self.used and self.expires_at >= utcnow()
