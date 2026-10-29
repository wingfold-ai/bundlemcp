from pydantic import BaseModel, Field


class ReencryptionSweep(BaseModel):
    """What one pass over the stored secrets did, and what still needs an older key."""

    rewritten: int = Field(
        default=0, ge=0, description="Values moved from an older key to the primary key"
    )
    remaining_on_old_key: int = Field(
        default=0,
        ge=0,
        description="Values still encrypted under an older key after the pass; the older key "
        "may be dropped once a pass reports zero",
    )
    undecryptable: int = Field(
        default=0,
        ge=0,
        description="Values no configured key decrypts; left unchanged and not counted as "
        "depending on an older key",
    )
    sealed: int = Field(
        default=0,
        ge=0,
        description="Servers whose static headers were still stored in plaintext and are now "
        "encrypted under the primary key",
    )
