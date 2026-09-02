import uuid
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey
from sqlmodel import Field, SQLModel


class UpstreamOAuthClient(SQLModel, table=True):
    __tablename__ = "upstream_oauth_clients"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the registration"
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), unique=True),
        description="Upstream server this client is registered with",
    )
    client_id: str | None = Field(
        default=None,
        description="Client id at the upstream authorization server; null until registered",
    )
    client_secret_encrypted: str | None = Field(  # DOM-3 / DEP-9
        default=None,
        description="Client secret, encrypted at rest. Never returned by the API",
    )
    metadata_: dict[str, Any] = Field(  # UPO-1
        default_factory=dict,
        sa_column=Column("metadata", JSON),
        description="Endpoints and scopes discovered from the upstream authorization server",
    )
