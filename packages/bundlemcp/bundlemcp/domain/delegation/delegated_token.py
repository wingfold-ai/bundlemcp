import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

DELEGATION_CLIENT_ID = "bundlemcp-delegation"  # the client every delegated token is issued to
DELEGATED_TOKEN_TTL_SECONDS = 300  # FWD-6
ENDPOINT_ACTOR_PREFIX = "endpoint:"


class DelegatedToken(BaseModel):
    """A token the gateway issued for one caller, valid only at one upstream server.

    It is the gateway's token exchange: the caller's authenticated identity is
    the subject, the upstream server is the audience, and the endpoint the
    call came through is the actor. Only its hash identifies it in storage.
    """

    model_config = ConfigDict(frozen=True)

    sub: str = Field(description="The caller: a user id or 'api_key:<id>'")
    email: str | None = Field(default=None, description="The caller's email, when known")
    server_id: uuid.UUID = Field(description="The upstream server the token is valid for")
    audience: str = Field(description="The upstream server's URL, reported as 'aud'")
    endpoint: str | None = Field(
        default=None, description="Name of the endpoint the caller came through"
    )
    expires_at: datetime = Field(description="When the token stops being accepted")

    def is_usable_at(self, now: datetime) -> bool:
        return self.expires_at >= now

    @property
    def actor(self) -> str | None:
        return f"{ENDPOINT_ACTOR_PREFIX}{self.endpoint}" if self.endpoint else None
