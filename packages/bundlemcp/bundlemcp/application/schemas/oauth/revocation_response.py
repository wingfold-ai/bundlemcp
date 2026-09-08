from pydantic import BaseModel, Field


class RevocationResponse(BaseModel):
    """Acknowledgement of a revocation request; always successful (RFC 7009)."""

    revoked: bool = Field(default=True, description="Always true; unknown tokens are ignored")
