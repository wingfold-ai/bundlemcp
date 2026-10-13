from pydantic import BaseModel, Field


class UpstreamBinding(BaseModel):
    """A session's lazy attachment to one upstream session."""

    server_name: str = Field(description="Upstream server this binding is for")
    upstream_session_id: str | None = Field(
        default=None,
        description="Session id the upstream issued; null until the first call establishes one",
    )
    identity_key: str | None = Field(
        default=None,
        description="The caller's subject when the binding was made. Recorded only: no "
        "upstream session is reused yet, so nothing reads it",
    )
