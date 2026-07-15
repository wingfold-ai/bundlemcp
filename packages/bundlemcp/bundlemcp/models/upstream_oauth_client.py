import uuid
from typing import Any

from sqlalchemy import JSON, Column, ForeignKey
from sqlmodel import Field, SQLModel


class UpstreamOAuthClient(SQLModel, table=True):
    __tablename__ = "upstream_oauth_clients"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), unique=True)
    )
    client_id: str | None = None
    client_secret_encrypted: str | None = None  # DOM-3 / DEP-9
    metadata_: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column("metadata", JSON)
    )  # discovered endpoints etc. (UPO-1)
