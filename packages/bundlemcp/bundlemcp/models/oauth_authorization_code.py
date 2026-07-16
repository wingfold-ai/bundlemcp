import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from bundlemcp.models.base import _ts


class OAuthAuthorizationCode(SQLModel, table=True):
    __tablename__ = "oauth_authorization_codes"

    code_hash: str = Field(primary_key=True)  # OAS-8: hashed at rest
    client_id: str = Field(
        sa_column=Column(ForeignKey("oauth_clients.client_id", ondelete="CASCADE"))
    )
    user_id: uuid.UUID = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE")))
    endpoint_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    )  # audience (OAS-10)
    redirect_uri: str
    scope: str = Field(default="mcp")
    code_challenge: str
    code_challenge_method: str = Field(default="S256")
    expires_at: datetime = Field(sa_column=_ts())
    used: bool = Field(default=False)  # single-use (OAS-3)
