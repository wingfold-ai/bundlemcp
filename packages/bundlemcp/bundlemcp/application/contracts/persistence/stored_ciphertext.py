import uuid

from pydantic import BaseModel, ConfigDict, Field


class StoredCiphertext(BaseModel):
    """One encrypted value as it sits in storage, addressed by the row that holds it."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(description="Identifier of the row holding the value")
    ciphertext: str = Field(repr=False, description="The value exactly as stored, still encrypted")
