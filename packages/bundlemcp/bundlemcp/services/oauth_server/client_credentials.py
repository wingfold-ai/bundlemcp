import base64
import binascii

from pydantic import BaseModel, ConfigDict, Field


class ClientCredentials(BaseModel):
    """What a client presented to identify itself at the token endpoint."""

    model_config = ConfigDict(frozen=True)

    client_id: str = Field(description="Client identifier, from the body or the Basic header")
    client_secret: str | None = Field(
        default=None, description="Client secret; absent for public clients"
    )

    @classmethod
    def from_basic_header(cls, authorization: str | None) -> "ClientCredentials | None":
        """Credentials carried as HTTP Basic, or None when the header is not Basic."""
        if not authorization or not authorization.lower().startswith("basic "):
            return None
        try:
            decoded = base64.b64decode(authorization[6:], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return None
        client_id, _, secret = decoded.partition(":")
        return cls(client_id=client_id, client_secret=secret or None)
