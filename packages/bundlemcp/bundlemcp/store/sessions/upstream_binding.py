from pydantic import BaseModel


class UpstreamBinding(BaseModel):
    """A session's lazy attachment to one upstream session."""

    server_name: str
    upstream_session_id: str | None = None
    identity_key: str | None = None  # caller sub + forwarded-credential hash (FWD-5)
