from pydantic import BaseModel, Field


class UpstreamBinding(BaseModel):
    """A session's lazy attachment to one upstream session."""

    server_name: str = Field(description="Upstream server this binding is for")
    upstream_session_id: str | None = Field(
        default=None,
        description="Session id the upstream issued; null until the first call establishes one",
    )
    identity_key: str | None = Field(  # AUTH-31
        default=None,
        description="Fingerprint of the caller and any forwarded credentials. A change means "
        "the binding belongs to a different identity and must not be reused",
    )
