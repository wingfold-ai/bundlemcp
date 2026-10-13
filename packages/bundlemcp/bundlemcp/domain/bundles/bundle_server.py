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
