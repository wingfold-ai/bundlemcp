from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field


class TokenPolicy(BaseModel):
    """How long what this authorization server issues stays valid.

    Read from runtime configuration when a request is served, so operators
    change lifetimes without a restart; the defaults are the values in effect
    when nothing is configured.
    """

    model_config = ConfigDict(frozen=True)

    access_token_ttl: timedelta = Field(  # OAS-4
        default=timedelta(hours=1),
        gt=timedelta(0),
        description="How long an access token authenticates before it must be refreshed",
    )
    refresh_token_ttl: timedelta = Field(  # OAS-4
        default=timedelta(days=7),
        gt=timedelta(0),
        description="How long a refresh token may be exchanged for a new pair",
    )
    authorization_code_ttl: timedelta = Field(  # OAS-3
        default=timedelta(minutes=10),
        gt=timedelta(0),
        description="How long a client has to redeem an authorization code",
    )
