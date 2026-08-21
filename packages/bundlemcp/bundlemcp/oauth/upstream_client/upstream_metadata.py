from pydantic import BaseModel


class UpstreamMetadata(BaseModel):
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    scopes_supported: list[str] = []
