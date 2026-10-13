import uuid

from pydantic import BaseModel, Field


class BundleServer(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the membership")
    bundle_id: uuid.UUID = Field(
        description="Bundle the server belongs to",
    )
    server_id: uuid.UUID = Field(
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
