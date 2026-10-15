"""The ``bundle_servers`` table, as SQLAlchemy sees it."""

import uuid

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel


class BundleServerRow(SQLModel, table=True):
    __tablename__ = "bundle_servers"
    __table_args__ = (UniqueConstraint("bundle_id", "server_id", name="uq_bundle_servers_pair"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, primary_key=True, description="Identifier of the membership"
    )
    bundle_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("bundles.id", ondelete="CASCADE"), index=True),
        description="Bundle the server belongs to",
    )
    server_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True),
        description="Server that belongs to the bundle",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this membership contributes tools; disabling hides them without "
        "losing their curation",
    )
    position: int = Field(
        default=0,
        ge=0,
        description="Place of the member in the bundle's member order, lowest first; decides "
        "which member answers first wherever more than one could",
    )
