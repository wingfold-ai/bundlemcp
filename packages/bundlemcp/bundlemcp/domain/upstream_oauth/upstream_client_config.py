from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UpstreamClientConfig(BaseModel):
    """The pre-registered client this gateway uses at one upstream authorization server."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(description="Client id at the upstream authorization server")
    client_secret: str | None = Field(
        default=None, repr=False, description="Decrypted client secret; absent for public clients"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Authorization server endpoints as configured or previously discovered",
    )
